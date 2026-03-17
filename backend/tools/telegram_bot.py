from __future__ import annotations

import logging
import time
from typing import Any, Callable

import requests

import config
from agent.run_config import RunConfig
from agent.tracker_agent import TrackerAgent


class TelegramBotClient:
    """Thin Telegram Bot API client for notifications and simple command polling."""

    def __init__(self) -> None:
        self.token = config.TELEGRAM_BOT_TOKEN
        self.default_chat_id = str(config.TELEGRAM_CHAT_ID).strip()
        self.enabled = config.TELEGRAM_ENABLED
        self.poll_timeout = max(1, config.TELEGRAM_POLL_TIMEOUT)
        self.log = logging.getLogger("telegram")
        self.last_error = ""

    @property
    def token_configured(self) -> bool:
        return bool(self.token)

    @property
    def auto_delivery_ready(self) -> bool:
        return self.enabled and self.token_configured and bool(self.default_chat_id)

    def get_status(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "token_configured": self.token_configured,
            "default_chat_configured": bool(self.default_chat_id),
            "auto_delivery_ready": self.auto_delivery_ready,
            "poll_timeout": self.poll_timeout,
            "last_error": self.last_error,
        }

    def _api_url(self, method: str) -> str:
        return f"https://api.telegram.org/bot{self.token}/{method}"

    def _request(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = requests.post(self._api_url(method), json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
        if not data.get("ok"):
            raise RuntimeError(data.get("description", "Telegram API request failed"))
        self.last_error = ""
        return data

    def test_connection(self) -> dict[str, Any]:
        if not self.token_configured:
            return {"ok": False, "message": "TELEGRAM_BOT_TOKEN is missing"}
        try:
            data = self._request("getMe", {})
            result = data.get("result") or {}
            return {
                "ok": True,
                "message": "Telegram API reachable",
                "bot_username": result.get("username", ""),
                "bot_name": result.get("first_name", ""),
            }
        except Exception as exc:
            self.last_error = str(exc)
            return {"ok": False, "message": str(exc)}

    def send_message(self, text: str, chat_id: str | None = None) -> bool:
        target_chat = str(chat_id or self.default_chat_id).strip()
        if not self.token_configured or not target_chat:
            return False
        try:
            self._request(
                "sendMessage",
                {
                    "chat_id": target_chat,
                    "text": text[:4096],
                    "disable_web_page_preview": True,
                },
            )
            return True
        except Exception as exc:
            self.last_error = str(exc)
            self.log.warning("Telegram send failed: %s", exc)
            return False

    def get_updates(self, offset: int | None = None, timeout: int | None = None) -> list[dict[str, Any]]:
        if not self.token_configured:
            return []
        payload: dict[str, Any] = {
            "timeout": timeout or self.poll_timeout,
            "allowed_updates": ["message"],
        }
        if offset is not None:
            payload["offset"] = offset
        try:
            return self._request("getUpdates", payload).get("result", [])
        except Exception as exc:
            self.last_error = str(exc)
            self.log.warning("Telegram polling failed: %s", exc)
            time.sleep(3)
            return []

    def notify_run_started(self, run_id: str, goal: str) -> bool:
        if not self.auto_delivery_ready:
            return False
        return self.send_message(
            f"Job Agent started\nRun: {run_id}\nGoal: {goal.strip() or 'config-only run'}"
        )

    def notify_progress(self, run_id: str, progress: dict[str, Any]) -> bool:
        if not self.auto_delivery_ready:
            return False
        agent = progress.get("agent", "Agent")
        phase = progress.get("phase", "working")
        message = progress.get("message", "Pipeline running.")
        return self.send_message(
            f"Pipeline update\nRun: {run_id}\nAgent: {agent}\nPhase: {phase}\n{message}"
        )

    def notify_job_result(self, run_id: str, result: dict[str, Any]) -> bool:
        if not self.auto_delivery_ready:
            return False
        job = result.get("job") or {}
        status = result.get("result", "Unknown")
        title = job.get("title", "Unknown role")
        company = job.get("company", "Unknown company")
        location = job.get("location", "")
        notes = (result.get("notes") or "").strip()
        lines = [
            "Job update",
            f"Run: {run_id}",
            f"Status: {status}",
            f"Role: {title}",
            f"Company: {company}",
        ]
        if location:
            lines.append(f"Location: {location}")
        if notes:
            lines.append(f"Notes: {notes[:500]}")
        return self.send_message("\n".join(lines))

    def notify_run_finished(
        self,
        run_id: str,
        *,
        status: str,
        message: str,
        payload: dict[str, Any] | None = None,
    ) -> bool:
        if not self.auto_delivery_ready:
            return False
        payload = payload or {}
        counts = payload.get("counts") or {}
        results = payload.get("results") or []
        final_results = [
            item
            for item in results
            if str(item.get("result", "")) in {"Applied", "DryRun"}
        ]
        if status != "completed" or not final_results:
            return False

        lines = [
            "Pipeline finished",
            f"Run: {run_id}",
            f"Status: {status}",
            message,
            "Counts: raw={raw_jobs} scored={scored_jobs} approved={approved_jobs} applied={applications_processed}".format(
                raw_jobs=counts.get("raw_jobs", 0),
                scored_jobs=counts.get("scored_jobs", 0),
                approved_jobs=counts.get("approved_jobs", 0),
                applications_processed=counts.get("applications_processed", len(final_results)),
            ),
            "Final applied jobs:",
        ]

        for item in final_results[:5]:
            job = item.get("job") or {}
            title = job.get("title", "Unknown role")
            company = job.get("company", "Unknown company")
            location = job.get("location", "")
            result = item.get("result", "Applied")
            notes = str(item.get("notes") or "").strip()
            summary = f"- {result}: {title} @ {company}"
            if location:
                summary += f" ({location})"
            lines.append(summary)
            if notes:
                lines.append(f"  Notes: {notes[:200]}")

        remaining = len(final_results) - 5
        if remaining > 0:
            lines.append(f"And {remaining} more applied result(s).")

        return self.send_message("\n".join(lines))


class TelegramCommandService:
    """Simple long-polling command loop for checking tracker state from Telegram."""

    def __init__(
        self,
        *,
        bot: TelegramBotClient,
        run_state_provider: Callable[[], dict[str, dict[str, Any]]],
        startup_status_provider: Callable[[], dict[str, Any]],
    ) -> None:
        self.bot = bot
        self.run_state_provider = run_state_provider
        self.startup_status_provider = startup_status_provider

    def _tracker(self) -> TrackerAgent:
        run_config = RunConfig.build(
            dry_run_override=True,
            max_scraped_jobs=1,
            max_scoring_jobs=1,
            max_applications=1,
            max_approved_candidates=1,
        )
        return TrackerAgent(run_config=run_config)

    def _is_allowed_chat(self, chat_id: str) -> bool:
        if not self.bot.default_chat_id:
            return True
        return str(chat_id) == self.bot.default_chat_id

    def _help_text(self) -> str:
        return (
            "Job Agent Telegram commands\n"
            "/help - show commands\n"
            "/status - current pipeline state\n"
            "/stats - tracker summary\n"
            "/history - latest tracked applications\n"
            "/startup - backend startup diagnostics"
        )

    def _format_status(self) -> str:
        runs = self.run_state_provider()
        active = [item for item in runs.values() if item.get("status") == "running"]
        if not active:
            return "No pipeline is running right now."

        lines = ["Active pipeline runs"]
        for item in active[:5]:
            progress = (item.get("payload") or {}).get("current_progress") or {}
            lines.append(
                f"- {item.get('run_id')} | {progress.get('agent', 'Agent')} | {progress.get('phase', 'running')}"
            )
            if progress.get("message"):
                lines.append(f"  {progress['message']}")
        return "\n".join(lines)

    def _format_stats(self) -> str:
        tracker = self._tracker()
        stats = tracker.get_stats()
        applied_today = tracker.get_applied_today()
        return (
            "Tracker stats\n"
            f"Total: {stats.get('total', 0)}\n"
            f"Applied: {stats.get('Applied', 0)}\n"
            f"DryRun: {stats.get('DryRun', 0)}\n"
            f"Failed: {stats.get('Failed', 0)}\n"
            f"Skipped: {stats.get('Skipped', 0)}\n"
            f"Today: {applied_today}"
        )

    def _format_history(self) -> str:
        tracker = self._tracker()
        records = tracker.get_recent_records(limit=5)
        if not records:
            return "No tracked applications yet."
        lines = ["Recent applications"]
        for record in records:
            lines.append(
                f"- {record.get('title', 'Unknown role')} @ {record.get('company', 'Unknown')} | {record.get('status', 'Unknown')}"
            )
        return "\n".join(lines)

    def _format_startup(self) -> str:
        startup = self.startup_status_provider() or {}
        if not startup:
            return "Startup diagnostics are not available yet."
        checks = startup.get("checks") or {}
        mongo = checks.get("mongodb") or {}
        cf = checks.get("cloudflare_workers_ai") or {}
        telegram = checks.get("telegram_bot") or {}
        return (
            "Backend startup\n"
            f"Overall OK: {startup.get('overall_ok')}\n"
            f"Cloudflare: {cf.get('ok')}\n"
            f"MongoDB: {mongo.get('ok')}\n"
            f"Telegram: {telegram.get('auto_delivery_ready')}"
        )

    def handle_update(self, update: dict[str, Any]) -> None:
        message = update.get("message") or {}
        text = (message.get("text") or "").strip()
        chat = message.get("chat") or {}
        chat_id = str(chat.get("id", ""))
        if not text or not chat_id:
            return
        if not self._is_allowed_chat(chat_id):
            self.bot.send_message("This chat is not authorized for Job Agent bot access.", chat_id=chat_id)
            return

        command = text.split()[0].lower()
        if command in {"/start", "/help"}:
            reply = self._help_text()
        elif command == "/status":
            reply = self._format_status()
        elif command == "/stats":
            reply = self._format_stats()
        elif command == "/history":
            reply = self._format_history()
        elif command == "/startup":
            reply = self._format_startup()
        else:
            reply = "Unknown command. Use /help to see available commands."

        self.bot.send_message(reply, chat_id=chat_id)

    def run_forever(self) -> None:
        if not self.bot.token_configured:
            raise RuntimeError("TELEGRAM_BOT_TOKEN is missing")
        self.bot.log.info("Telegram polling service started.")
        offset: int | None = None
        try:
            while True:
                updates = self.bot.get_updates(offset=offset, timeout=self.bot.poll_timeout)
                for update in updates:
                    offset = int(update["update_id"]) + 1
                    self.handle_update(update)
        except KeyboardInterrupt:
            self.bot.log.info("Telegram polling stopped by user.")
