from __future__ import annotations

import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

import config
import requests
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

try:
    from pymongo import MongoClient
except Exception:  # pragma: no cover
    MongoClient = None

try:
    import firebase_admin
    from firebase_admin import auth as firebase_auth
    from firebase_admin import credentials as firebase_credentials
except Exception:  # pragma: no cover
    firebase_admin = None
    firebase_auth = None
    firebase_credentials = None

from agent.run_config import RunConfig
from agent.tracker_agent import TrackerAgent
from api.models import (
    AsyncRunResponse,
    DocsSummaryResponse,
    FirebaseLoginRequest,
    FeatureResponse,
    FirebaseUserResponse,
    RunRequest,
    RunResponse,
    TelegramTestRequest,
    TrackerStatusUpdateRequest,
)
from api.service import execute_pipeline
from tools.telegram_bot import TelegramBotClient

app = FastAPI(
    title="Job Agent Backend API",
    version="1.3.0",
    description="FastAPI surface for the job application pipeline, tracker, and Telegram integration.",
    openapi_tags=[
        {"name": "auth", "description": "Firebase authentication and current-user endpoints."},
        {"name": "diagnostics", "description": "Startup, health, config, and API discovery endpoints."},
        {"name": "pipeline", "description": "Run the job pipeline and inspect active or completed runs."},
        {"name": "tracker", "description": "Read or update tracked application records."},
        {"name": "telegram", "description": "Inspect and test Telegram bot integration."},
    ],
)
log = logging.getLogger("api")

_RUNS: dict[str, dict[str, Any]] = {}
_RUNS_LOCK = threading.Lock()
_STARTUP_STATUS: dict[str, Any] = {}
_FIREBASE_READY = False
_FIREBASE_ERROR = ""
_TELEGRAM_BOT = TelegramBotClient()


def _set_run_state(run_id: str, *, status_value: str, message: str, payload: dict[str, Any] | None = None) -> None:
    with _RUNS_LOCK:
        current = _RUNS.get(run_id, {})
        merged_payload = dict(current.get("payload") or {})
        if payload:
            merged_payload.update(payload)
        _RUNS[run_id] = {
            "run_id": run_id,
            "status": status_value,
            "message": message,
            "payload": merged_payload,
        }


def _safe_notify_run_finished(run_id: str, *, status: str, message: str, payload: dict[str, Any] | None = None) -> None:
    try:
        _TELEGRAM_BOT.notify_run_finished(run_id, status=status, message=message, payload=payload)
    except Exception as exc:
        log.warning("Telegram final notification failed but pipeline result is preserved: %s", exc)


def _update_run_progress(run_id: str, progress: dict[str, Any]) -> None:
    with _RUNS_LOCK:
        current = _RUNS.get(run_id, {})
        payload = dict(current.get("payload") or {})
        payload["current_progress"] = progress
        _RUNS[run_id] = {
            "run_id": run_id,
            "status": current.get("status", "running"),
            "message": progress.get("message", current.get("message", "Pipeline running.")),
            "payload": payload,
        }


security = HTTPBearer(auto_error=False)

frontend_origins = getattr(
    config,
    "FRONTEND_ORIGINS",
    ["http://localhost:5173", "http://127.0.0.1:5173"],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=frontend_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _firebase_service_account_path() -> Path:
    configured = getattr(config, "FIREBASE_SERVICE_ACCOUNT_PATH", Path("serviceAccountKey.json"))
    path = Path(configured)
    if not path.is_absolute():
        path = Path(__file__).resolve().parents[1] / path
    return path


def _init_firebase_admin() -> None:
    global _FIREBASE_READY, _FIREBASE_ERROR
    if firebase_admin is None:
        _FIREBASE_READY = False
        _FIREBASE_ERROR = "firebase-admin not installed"
        return

    if firebase_admin._apps:
        _FIREBASE_READY = True
        _FIREBASE_ERROR = ""
        return

    key_path = _firebase_service_account_path()
    if not key_path.exists():
        _FIREBASE_READY = False
        _FIREBASE_ERROR = f"Service account key not found at {key_path}"
        return

    try:
        cred = firebase_credentials.Certificate(str(key_path))
        firebase_admin.initialize_app(cred)
        _FIREBASE_READY = True
        _FIREBASE_ERROR = ""
    except Exception as e:
        _FIREBASE_READY = False
        _FIREBASE_ERROR = str(e)


def _verify_token_or_401(credentials: HTTPAuthorizationCredentials | None) -> dict[str, Any]:
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Bearer token",
        )
    if not _FIREBASE_READY or firebase_auth is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Firebase auth not ready: {_FIREBASE_ERROR}",
        )
    try:
        decoded = firebase_auth.verify_id_token(
            credentials.credentials,
            clock_skew_seconds=60,
        )
        return decoded
    except Exception as e:
        message = str(e)
        if "Token used too early" in message:
            message = (
                "Invalid Firebase token: token timestamp is ahead of the server clock. "
                "Sync your system date/time and try signing in again."
            )
        else:
            message = f"Invalid Firebase token: {e}"
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=message,
        )


def require_auth(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    return _verify_token_or_401(credentials)


def _check_cloudflare() -> dict[str, Any]:
    if not config.CF_ACCOUNT_ID or not config.CF_API_TOKEN:
        return {
            "required": True,
            "configured": False,
            "ok": False,
            "message": "Missing CF_ACCOUNT_ID or CF_API_TOKEN",
        }

    headers = {
        "Authorization": f"Bearer {config.CF_API_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 1,
        "temperature": 0,
    }
    try:
        resp = requests.post(config.CF_API_URL, headers=headers, json=payload, timeout=30)
        reachable_codes = {200, 400, 401, 403, 404, 405, 429}
        return {
            "required": True,
            "configured": True,
            "ok": resp.status_code in reachable_codes,
            "status_code": resp.status_code,
            "model": config.CF_MODEL,
            "message": "Reachable" if resp.status_code in reachable_codes else "Unexpected response",
        }
    except Exception as e:
        return {
            "required": True,
            "configured": True,
            "ok": False,
            "model": config.CF_MODEL,
            "message": f"Connection failed: {e}",
        }


def _check_mongodb() -> dict[str, Any]:
    if not config.MONGODB_URI:
        return {
            "required": False,
            "configured": False,
            "ok": False,
            "message": "MONGODB_URI not set (Excel fallback mode)",
        }
    if MongoClient is None:
        return {
            "required": False,
            "configured": True,
            "ok": False,
            "message": "pymongo not installed",
        }

    try:
        client = MongoClient(config.MONGODB_URI, serverSelectionTimeoutMS=5000)
        client.admin.command("ping")
        return {
            "required": False,
            "configured": True,
            "ok": True,
            "db": config.MONGODB_DB,
            "collection": config.MONGODB_COLLECTION,
            "message": "Connected",
        }
    except Exception as e:
        return {
            "required": False,
            "configured": True,
            "ok": False,
            "db": config.MONGODB_DB,
            "collection": config.MONGODB_COLLECTION,
            "message": f"Connection failed: {e}",
        }


def _check_firebase() -> dict[str, Any]:
    key_path = _firebase_service_account_path()
    return {
        "required": True,
        "configured": key_path.exists(),
        "ok": _FIREBASE_READY,
        "service_account_path": str(key_path),
        "message": "Ready" if _FIREBASE_READY else (_FIREBASE_ERROR or "Not initialized"),
    }


def _check_telegram() -> dict[str, Any]:
    status_info = _TELEGRAM_BOT.get_status()
    return {
        "required": False,
        "configured": status_info["token_configured"],
        "ok": status_info["token_configured"],
        "enabled": status_info["enabled"],
        "auto_delivery_ready": status_info["auto_delivery_ready"],
        "default_chat_configured": status_info["default_chat_configured"],
        "message": (
            "Ready for notifications"
            if status_info["auto_delivery_ready"]
            else "Token loaded" if status_info["token_configured"] else "Telegram bot not configured"
        ),
    }


def _build_startup_status() -> dict[str, Any]:
    checks = {
        "cloudflare_workers_ai": _check_cloudflare(),
        "mongodb": _check_mongodb(),
        "firebase_auth": _check_firebase(),
        "telegram_bot": _check_telegram(),
        "resume_file": {
            "required": False,
            "configured": True,
            "ok": config.USER_RESUME_PATH.exists(),
            "path": str(config.USER_RESUME_PATH),
            "message": "Found" if config.USER_RESUME_PATH.exists() else "Missing resume file",
        },
    }
    overall_ok = (
        checks["firebase_auth"]["ok"]
        and (checks["mongodb"]["ok"] or not checks["mongodb"]["configured"])
        and (checks["resume_file"]["ok"] or not checks["resume_file"]["required"])
    )
    return {
        "service": "job-agent-backend",
        "overall_ok": overall_ok,
        "cloudflare_warning": not checks["cloudflare_workers_ai"]["ok"],
        "checked_at": datetime.now().isoformat(timespec="seconds"),
        "checks": checks,
    }


@app.on_event("startup")
def startup_diagnostics() -> None:
    global _STARTUP_STATUS
    _init_firebase_admin()
    _STARTUP_STATUS = _build_startup_status()
    cf = _STARTUP_STATUS["checks"]["cloudflare_workers_ai"]
    mongo = _STARTUP_STATUS["checks"]["mongodb"]
    fb = _STARTUP_STATUS["checks"]["firebase_auth"]
    telegram = _STARTUP_STATUS["checks"]["telegram_bot"]
    resume = _STARTUP_STATUS["checks"]["resume_file"]
    log.warning(
        "Startup diagnostics | overall_ok=%s | CF(ok=%s, model=%s) | Firebase(ok=%s) | Mongo(ok=%s) | Telegram(configured=%s, auto_delivery=%s) | Resume(ok=%s, path=%s)",
        _STARTUP_STATUS["overall_ok"],
        cf.get("ok"),
        cf.get("model"),
        fb.get("ok"),
        mongo.get("ok"),
        telegram.get("configured"),
        telegram.get("auto_delivery_ready"),
        resume.get("ok"),
        resume.get("path"),
    )


def _redacted_config() -> dict[str, Any]:
    return {
        "cf_model": config.CF_MODEL,
        "headless": config.HEADLESS,
        "use_temp_browser_profile": config.USE_TEMP_BROWSER_PROFILE,
        "dry_run_default": config.DRY_RUN,
        "min_confidence_score": config.MIN_CONFIDENCE_SCORE,
        "max_applications_per_run": config.MAX_APPLICATIONS_PER_RUN,
        "user_location": config.USER_LOCATION,
        "target_roles": config.USER_TARGET_ROLES,
        "target_locations": config.USER_TARGET_LOCATIONS,
        "mongodb_enabled": bool(config.MONGODB_URI),
        "firebase_ready": _FIREBASE_READY,
        "telegram_enabled": config.TELEGRAM_ENABLED,
        "telegram_default_chat_configured": bool(config.TELEGRAM_CHAT_ID),
        "log_file_path": str(config.LOG_FILE_PATH),
        "excel_file_path": str(config.EXCEL_FILE_PATH),
    }


def _feature_map() -> dict[str, Any]:
    return {
        "auth": {
            "firebase_login": "/api/v1/auth/firebase-login",
            "me": "/api/v1/me",
        },
        "diagnostics": {
            "health": "/api/v1/health",
            "startup": "/api/v1/startup",
            "config": "/api/v1/config",
            "features": "/api/v1/features",
        },
        "pipeline": {
            "run_sync": "/api/v1/run",
            "run_async": "/api/v1/run/async",
            "run_status": "/api/v1/run/{run_id}",
            "runs_overview": "/api/v1/runs",
        },
        "tracker": {
            "stats": "/api/v1/tracker/stats",
            "history": "/api/v1/tracker/history",
            "update_status": "/api/v1/tracker/update-status",
        },
        "telegram": {
            "status": "/api/v1/telegram/status",
            "test_message": "/api/v1/telegram/test",
        },
    }


def _docs_summary() -> dict[str, Any]:
    return {
        "authentication": {
            "required": True,
            "flow": [
                "POST /api/v1/auth/firebase-login",
                "Use returned Firebase identity token as Bearer token",
                "Call protected endpoints",
            ],
        },
        "pipeline": {
            "entrypoints": ["POST /api/v1/run", "POST /api/v1/run/async"],
            "outputs": [
                "search profile",
                "approved jobs",
                "cover letters",
                "agent flow",
                "submission results",
            ],
        },
        "tracker": {
            "read": ["GET /api/v1/tracker/stats", "GET /api/v1/tracker/history"],
            "write": ["POST /api/v1/tracker/update-status"],
        },
        "telegram": {
            "readiness": ["GET /api/v1/telegram/status", "POST /api/v1/telegram/test"],
            "notes": [
                "Telegram sends a single final summary after the run completes with applied results",
                "Runtime delivery still depends on network access to api.telegram.org",
            ],
        },
    }


@app.get("/api/v1/docs-summary", response_model=DocsSummaryResponse, tags=["diagnostics"], summary="Return a frontend-friendly backend capability summary")
def docs_summary(user: dict[str, Any] = Depends(require_auth)) -> DocsSummaryResponse:
    _ = user
    return DocsSummaryResponse(service="job-agent-backend", version=app.version, sections=_docs_summary())


@app.get("/api/v1/features", response_model=FeatureResponse, tags=["diagnostics"], summary="Return discoverable backend feature endpoints")
def features(user: dict[str, Any] = Depends(require_auth)) -> FeatureResponse:
    _ = user
    return FeatureResponse(service="job-agent-backend", features=_feature_map())


@app.get("/api/v1/health", tags=["diagnostics"], summary="Check basic API liveness")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "job-agent-backend",
        "startup_overall_ok": _STARTUP_STATUS.get("overall_ok"),
    }


@app.get("/api/v1/startup", tags=["diagnostics"], summary="Inspect startup dependency diagnostics")
def startup_status() -> dict[str, Any]:
    if not _STARTUP_STATUS:
        return {"status": "pending", "message": "Startup checks not executed yet."}
    return _STARTUP_STATUS


@app.get("/api/v1/config", tags=["diagnostics"], summary="Preview safe backend configuration")
def config_preview() -> dict[str, Any]:
    return _redacted_config()


@app.post("/api/v1/auth/firebase-login", response_model=FirebaseUserResponse, tags=["auth"], summary="Validate Firebase token and return user profile")
def firebase_login(request: FirebaseLoginRequest) -> FirebaseUserResponse:
    token_data = _verify_token_or_401(
        HTTPAuthorizationCredentials(scheme="Bearer", credentials=request.id_token)
    )
    return FirebaseUserResponse(
        uid=token_data.get("uid", ""),
        email=token_data.get("email", ""),
        name=token_data.get("name", ""),
        picture=token_data.get("picture", ""),
    )


@app.get("/api/v1/me", response_model=FirebaseUserResponse, tags=["auth"], summary="Return the authenticated user")
def me(user: dict[str, Any] = Depends(require_auth)) -> FirebaseUserResponse:
    return FirebaseUserResponse(
        uid=user.get("uid", ""),
        email=user.get("email", ""),
        name=user.get("name", ""),
        picture=user.get("picture", ""),
    )


@app.get("/api/v1/tracker/stats", tags=["tracker"], summary="Return tracker aggregate statistics")
def tracker_stats(user: dict[str, Any] = Depends(require_auth)) -> dict[str, Any]:
    _ = user
    rc = RunConfig.build(
        dry_run_override=True,
        max_scraped_jobs=1,
        max_scoring_jobs=1,
        max_applications=1,
        max_approved_candidates=1,
    )
    tracker = TrackerAgent(run_config=rc)
    return {
        "stats": tracker.get_stats(),
        "applied_today": tracker.get_applied_today(),
    }


@app.get("/api/v1/tracker/history", tags=["tracker"], summary="Return recent tracked application history")
def tracker_history(user: dict[str, Any] = Depends(require_auth)) -> dict[str, Any]:
    _ = user
    rc = RunConfig.build(
        dry_run_override=True,
        max_scraped_jobs=1,
        max_scoring_jobs=1,
        max_applications=1,
        max_approved_candidates=1,
    )
    tracker = TrackerAgent(run_config=rc)
    records = tracker.get_recent_records(limit=10)
    return {
        "backend": tracker.get_backend_info(),
        "total_recent": len(records),
        "records": records,
    }


@app.get("/api/v1/telegram/status", tags=["telegram"], summary="Inspect Telegram bot readiness")
def telegram_status(user: dict[str, Any] = Depends(require_auth)) -> dict[str, Any]:
    _ = user
    return _check_telegram()


@app.post("/api/v1/telegram/test", tags=["telegram"], summary="Send a Telegram test message")
def telegram_test(
    request: TelegramTestRequest,
    user: dict[str, Any] = Depends(require_auth),
) -> dict[str, Any]:
    _ = user
    sent = _TELEGRAM_BOT.send_message(request.message)
    return {
        "ok": sent,
        "telegram": _check_telegram(),
    }


@app.post("/api/v1/run", response_model=RunResponse, tags=["pipeline"], summary="Run the pipeline synchronously")
def run_pipeline(
    request: RunRequest,
    user: dict[str, Any] = Depends(require_auth),
) -> RunResponse:
    _ = user
    api_run_id = f"api-run-sync-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}"
    _set_run_state(api_run_id, status_value="running", message="Pipeline started.", payload={})
    try:
        outcome = execute_pipeline(
            goal=request.goal,
            config_only=request.config_only,
            dry_run=request.dry_run,
            easy_apply_only=request.easy_apply_only,
            max_scraped_jobs=request.max_scraped_jobs,
            max_scoring_jobs=request.max_scoring_jobs,
            max_applications=request.max_applications,
            submission_target_successes=request.submission_target_successes,
            max_approved_candidates=request.max_approved_candidates,
            linkedin_email=request.linkedin_email,
            linkedin_password=request.linkedin_password,
            resume_file_name=request.resume_file_name,
            resume_file_b64=request.resume_file_b64,
            work_mode_preference=request.work_mode_preference,
            progress_callback=lambda progress: _update_run_progress(api_run_id, progress),
        )
        _set_run_state(api_run_id, status_value=outcome["status"], message=outcome["message"], payload=outcome["payload"])
        _safe_notify_run_finished(api_run_id, status=outcome["status"], message=outcome["message"], payload=outcome.get("payload") or {})
        return RunResponse(**outcome)
    except Exception as e:
        _set_run_state(api_run_id, status_value="failed", message=str(e), payload={})
        _safe_notify_run_finished(api_run_id, status="failed", message=str(e), payload={})
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/run/async", response_model=AsyncRunResponse, tags=["pipeline"], summary="Start the pipeline asynchronously")
def run_pipeline_async(
    request: RunRequest,
    user: dict[str, Any] = Depends(require_auth),
) -> AsyncRunResponse:
    _ = user
    run_id = f"api-run-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}"
    _set_run_state(run_id, status_value="running", message="Pipeline started.", payload={})

    def _worker() -> None:
        try:
            outcome = execute_pipeline(
                goal=request.goal,
                config_only=request.config_only,
                dry_run=request.dry_run,
                easy_apply_only=request.easy_apply_only,
                max_scraped_jobs=request.max_scraped_jobs,
                max_scoring_jobs=request.max_scoring_jobs,
                max_applications=request.max_applications,
                submission_target_successes=request.submission_target_successes,
                max_approved_candidates=request.max_approved_candidates,
                linkedin_email=request.linkedin_email,
                linkedin_password=request.linkedin_password,
                resume_file_name=request.resume_file_name,
                resume_file_b64=request.resume_file_b64,
                work_mode_preference=request.work_mode_preference,
                progress_callback=lambda progress: _update_run_progress(run_id, progress),
            )
            _set_run_state(run_id, status_value=outcome["status"], message=outcome["message"], payload=outcome["payload"])
            _safe_notify_run_finished(run_id, status=outcome["status"], message=outcome["message"], payload=outcome.get("payload") or {})
        except Exception as e:
            _set_run_state(run_id, status_value="failed", message=str(e), payload={})
            _safe_notify_run_finished(run_id, status="failed", message=str(e), payload={})

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    return AsyncRunResponse(run_id=run_id, status="running")


@app.get("/api/v1/run/{run_id}", response_model=RunResponse, tags=["pipeline"], summary="Get status for a pipeline run")
def get_run(
    run_id: str,
    user: dict[str, Any] = Depends(require_auth),
) -> RunResponse:
    _ = user
    with _RUNS_LOCK:
        data = _RUNS.get(run_id)
    if not data:
        raise HTTPException(status_code=404, detail="Run not found")
    return RunResponse(**data)







