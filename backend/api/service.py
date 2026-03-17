from __future__ import annotations

import base64
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import config
from agent.critic_agent import CriticAgent
from agent.manager_agent import ManagerAgent
from agent.planner_agent import JobListing, PlannerAgent
from agent.run_config import RunConfig
from agent.submission_agent import ApplicationResult, SubmissionAgent
from agent.tracker_agent import TrackerAgent
from main import run_scrapers
from tools.agent_jsonl import append_jsonl
from tools.cover_letter import CoverLetterAgent
from tools.resume_tools import extract_skills, summarise_resume


def _emit_progress(
    progress_callback,
    *,
    agent: str,
    phase: str,
    message: str,
    extra: dict[str, Any] | None = None,
) -> None:
    if progress_callback is None:
        return
    progress_callback(
        {
            "agent": agent,
            "phase": phase,
            "message": message,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "extra": extra or {},
        }
    )


def _job_to_dict(job: JobListing) -> dict[str, Any]:
    return {
        "job_id": job.job_id,
        "platform": job.platform,
        "title": job.title,
        "company": job.company,
        "location": job.location,
        "work_mode": job.work_mode,
        "salary": job.salary,
        "url": job.url,
        "date_posted": job.date_posted,
        "confidence_score": job.confidence_score,
        "cover_letter_hint": job.cover_letter_hint,
    }


def _result_to_dict(result: ApplicationResult) -> dict[str, Any]:
    return {
        "job": _job_to_dict(result.job),
        "result": result.result.value,
        "notes": result.notes,
    }


def _build_agent_flow(
    *,
    profile: Any,
    raw_jobs: list[JobListing],
    scored_jobs: list[JobListing],
    approved_jobs: list[JobListing],
    cover_letters: dict[str, str],
    results: list[ApplicationResult],
    storage_target: str | None = None,
) -> list[dict[str, Any]]:
    success_count = sum(1 for item in results if item.result.value in ("Applied", "DryRun"))
    attempted_count = len(results)
    return [
        {
            "agent": "ManagerAgent",
            "title": "Understood your job goal",
            "status": "completed",
            "summary": f"Searching for {', '.join(profile.roles)} in {', '.join(profile.locations)}.",
        },
        {
            "agent": "PlannerAgent",
            "title": "Built search plan and scored scraped jobs",
            "status": "completed",
            "summary": f"Scraped {len(raw_jobs)} jobs and kept {len(scored_jobs)} after scoring.",
        },
        {
            "agent": "CriticAgent",
            "title": "Filtered to strongest candidates",
            "status": "completed" if approved_jobs else "blocked",
            "summary": f"Approved {len(approved_jobs)} jobs for submission.",
        },
        {
            "agent": "CoverLetterAgent",
            "title": "Generated tailored cover letters",
            "status": "completed" if cover_letters else "partial",
            "summary": f"Prepared {len(cover_letters)} job-specific cover letters from the resume context.",
        },
        {
            "agent": "SubmissionAgent",
            "title": "Tried jobs in fallback order until success",
            "status": "completed" if success_count else ("partial" if attempted_count else "blocked"),
            "summary": f"Attempted {attempted_count} jobs and finished with {success_count} successful application(s).",
        },
        {
            "agent": "TrackerAgent",
            "title": "Stored run outcomes",
            "status": "completed" if storage_target else "pending",
            "summary": f"Tracking backend: {storage_target or 'Not available'}",
        },
    ]


def _safe_resume_filename(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", (name or "resume.pdf").strip())
    if not cleaned:
        cleaned = "resume.pdf"
    if len(cleaned) > 120:
        cleaned = cleaned[-120:]
    return cleaned


def _materialize_runtime_resume(*, run_id: str, file_name: str, file_b64: str) -> Path:
    decoded = base64.b64decode(file_b64, validate=True)
    if not decoded:
        raise ValueError("Uploaded resume file is empty")

    resume_dir = Path("data") / "runtime_resumes"
    resume_dir.mkdir(parents=True, exist_ok=True)
    safe_name = _safe_resume_filename(file_name)
    target = resume_dir / f"{run_id}_{safe_name}"
    target.write_bytes(decoded)
    return target


def execute_pipeline(
    *,
    goal: str,
    config_only: bool,
    dry_run: bool,
    easy_apply_only: bool,
    max_scraped_jobs: int,
    max_scoring_jobs: int,
    max_applications: int,
    submission_target_successes: int = 1,
    max_approved_candidates: int,
    linkedin_email: str = "",
    linkedin_password: str = "",
    resume_file_name: str = "",
    resume_file_b64: str = "",
    work_mode_preference: str = "any",
    progress_callback=None,
) -> dict[str, Any]:
    original_email = config.LINKEDIN_EMAIL
    original_password = config.LINKEDIN_PASSWORD
    original_resume_path = config.USER_RESUME_PATH
    original_use_temp_browser_profile = config.USE_TEMP_BROWSER_PROFILE
    runtime_resume_path: Path | None = None

    run_config = RunConfig.build(
        dry_run_override=dry_run,
        max_scraped_jobs=max_scraped_jobs,
        max_scoring_jobs=max_scoring_jobs,
        max_applications=max_applications,
        max_approved_candidates=max_approved_candidates,
    )

    context_path = Path("data") / f"agent_context_{run_config.run_id}.jsonl"
    context_path.parent.mkdir(parents=True, exist_ok=True)
    context_path.write_text("", encoding="utf-8")

    try:
        _emit_progress(
            progress_callback,
            agent="ManagerAgent",
            phase="starting",
            message="Preparing runtime inputs and loading the job goal.",
        )
        use_runtime_linkedin_credentials = bool(
            linkedin_email.strip() and linkedin_password
        )
        if linkedin_email.strip():
            config.LINKEDIN_EMAIL = linkedin_email.strip()
        if linkedin_password:
            config.LINKEDIN_PASSWORD = linkedin_password
        if use_runtime_linkedin_credentials:
            config.USE_TEMP_BROWSER_PROFILE = True
        if resume_file_b64.strip():
            runtime_resume_path = _materialize_runtime_resume(
                run_id=run_config.run_id,
                file_name=resume_file_name,
                file_b64=resume_file_b64,
            )
            config.USER_RESUME_PATH = runtime_resume_path

        manager = ManagerAgent(run_config=run_config)
        if config_only or not goal.strip():
            profile = manager.build_profile_from_config()
        else:
            try:
                profile = manager.run(goal)
            except Exception:
                profile = manager.build_profile_from_config()

        profile.dry_run = run_config.dry_run
        requested_work_mode = (work_mode_preference or "any").strip().lower()
        if requested_work_mode in {"any", "remote", "onsite", "hybrid"}:
            profile.work_mode = requested_work_mode
        _emit_progress(
            progress_callback,
            agent="PlannerAgent",
            phase="planning",
            message="Building search queries from the parsed profile.",
            extra={"roles": profile.roles, "locations": profile.locations},
        )
        append_jsonl(
            context_path,
            "search_profile",
            {"goal": profile.goal, "profile": profile, "run_id": run_config.run_id},
        )

        planner = PlannerAgent(run_config=run_config)
        queries = planner.build_search_queries(profile)
        for query in queries:
            query["easy_apply_only"] = easy_apply_only
            query["max_jobs"] = run_config.max_scraped_jobs

        append_jsonl(context_path, "search_queries", {"queries": queries, "run_id": run_config.run_id})

        _emit_progress(
            progress_callback,
            agent="TrackerAgent",
            phase="loading-history",
            message="Checking previously tracked applications.",
        )
        tracker = TrackerAgent(run_config=run_config)
        applied_ids = tracker.get_applied_ids()

        _emit_progress(
            progress_callback,
            agent="PlannerAgent",
            phase="scraping",
            message="Scraping matching LinkedIn jobs.",
            extra={"max_scraped_jobs": run_config.max_scraped_jobs},
        )
        raw_jobs = run_scrapers(queries, run_config=run_config, max_total_jobs=run_config.max_scraped_jobs)
        append_jsonl(
            context_path,
            "raw_jobs",
            {"count": len(raw_jobs), "jobs": raw_jobs, "run_id": run_config.run_id},
        )

        raw_jobs = raw_jobs[: run_config.max_scoring_jobs]
        append_jsonl(
            context_path,
            "shortlisted_jobs",
            {"count": len(raw_jobs), "jobs": raw_jobs, "run_id": run_config.run_id},
        )

        if not raw_jobs:
            _emit_progress(
            progress_callback,
            agent="TrackerAgent",
            phase="completed",
            message="Pipeline completed successfully.",
            extra={"applications_processed": applied_count},
        )

        return {
                "run_id": run_config.run_id,
                "status": "no_jobs",
                "message": "No jobs found from scrapers.",
                "payload": {
                    "profile": {
                        "goal": profile.goal,
                        "roles": profile.roles,
                        "locations": profile.locations,
                        "dry_run": profile.dry_run,
                    },
                    "runtime_inputs": {
                        "linkedin_email_provided": bool(linkedin_email.strip()),
                        "resume_uploaded": runtime_resume_path is not None,
                    },
                    "context_path": str(context_path),
                },
            }

        _emit_progress(
            progress_callback,
            agent="PlannerAgent",
            phase="scoring",
            message="Scoring scraped jobs against the resume and target profile.",
            extra={"raw_jobs": len(raw_jobs)},
        )
        scored_jobs = planner.run(profile, raw_jobs, applied_ids)
        append_jsonl(
            context_path,
            "scored_jobs",
            {"count": len(scored_jobs), "jobs": scored_jobs, "run_id": run_config.run_id},
        )

        if not scored_jobs:
            return {
                "run_id": run_config.run_id,
                "status": "no_scored_jobs",
                "message": "No jobs passed scoring/filtering.",
                "payload": {
                    "profile": {
                        "goal": profile.goal,
                        "roles": profile.roles,
                        "locations": profile.locations,
                        "dry_run": profile.dry_run,
                    },
                    "runtime_inputs": {
                        "linkedin_email_provided": bool(linkedin_email.strip()),
                        "resume_uploaded": runtime_resume_path is not None,
                    },
                    "context_path": str(context_path),
                },
            }

        _emit_progress(
            progress_callback,
            agent="CriticAgent",
            phase="reviewing",
            message="Reviewing scored jobs and selecting the strongest candidates.",
            extra={"scored_jobs": len(scored_jobs)},
        )
        critic = CriticAgent(run_config=run_config)
        approved_jobs = critic.run(scored_jobs, profile)
        approved_jobs = approved_jobs[: max(10, run_config.max_approved_candidates)]
        append_jsonl(
            context_path,
            "approved_jobs",
            {"count": len(approved_jobs), "jobs": approved_jobs, "run_id": run_config.run_id},
        )

        if not approved_jobs:
            return {
                "run_id": run_config.run_id,
                "status": "no_approved_jobs",
                "message": "Critic did not approve any jobs.",
                "payload": {
                    "scored_jobs": [_job_to_dict(j) for j in scored_jobs],
                    "runtime_inputs": {
                        "linkedin_email_provided": bool(linkedin_email.strip()),
                        "resume_uploaded": runtime_resume_path is not None,
                    },
                    "context_path": str(context_path),
                },
            }

        _emit_progress(
            progress_callback,
            agent="CoverLetterAgent",
            phase="writing",
            message="Generating tailored cover letters for approved jobs.",
            extra={"approved_jobs": len(approved_jobs)},
        )
        resume_skills = extract_skills(config.USER_RESUME_PATH)
        try:
            resume_text = summarise_resume(
                config.USER_RESUME_PATH,
                llm_caller=CoverLetterAgent(run_config=run_config).ask_llm,
            )
        except Exception:
            resume_text = summarise_resume(config.USER_RESUME_PATH)

        if resume_skills:
            resume_text = f"{resume_text}\n\nRelevant skills: {', '.join(resume_skills[:20])}"

        # Hierarchical fallback: keep trying next approved jobs until target successes are reached.
        submission_target_successes = max(1, submission_target_successes)
        jobs_to_apply = approved_jobs
        cover_letter_agent = CoverLetterAgent(run_config=run_config)
        cover_letters: dict[str, str] = {}
        for job in jobs_to_apply:
            try:
                generated = cover_letter_agent.generate(job, resume_text).strip()
                if generated:
                    cover_letters[job.job_id] = generated
            except Exception as e:
                cover_letter_agent.log.warning(
                    f"Cover letter generation failed for {job.title} @ {job.company}: {e}"
                )

        append_jsonl(
            context_path,
            "cover_letters",
            {
                "generated_count": len(cover_letters),
                "job_ids": list(cover_letters.keys()),
                "run_id": run_config.run_id,
            },
        )

        _emit_progress(
            progress_callback,
            agent="SubmissionAgent",
            phase="applying",
            message="Attempting applications in fallback order until success.",
            extra={"jobs_to_try": len(jobs_to_apply), "target_successes": submission_target_successes},
        )
        submission_run_config = RunConfig(
            run_id=run_config.run_id,
            dry_run=run_config.dry_run,
            max_scraped_jobs=run_config.max_scraped_jobs,
            max_scoring_jobs=run_config.max_scoring_jobs,
            max_applications=submission_target_successes,
            max_approved_candidates=run_config.max_approved_candidates,
        )
        submission = SubmissionAgent(run_config=submission_run_config)
        results = submission.run(
            jobs_to_apply,
            cover_letters,
            resume_summary=resume_text,
            applied_ids=applied_ids,
        )
        append_jsonl(context_path, "submission_results", {"results": results, "run_id": run_config.run_id})

        _emit_progress(
            progress_callback,
            agent="TrackerAgent",
            phase="saving",
            message="Saving application results to the tracker backend.",
            extra={"results": len(results)},
        )
        tracker.run(results)

        applied_count = sum(1 for r in results if r.result.value in ("Applied", "DryRun"))
        storage_target = (
            f"MongoDB: {config.MONGODB_DB}.{config.MONGODB_COLLECTION}"
            if tracker.use_mongodb
            else f"Excel: {config.EXCEL_FILE_PATH}"
        )

        cover_letter_entries = [
            {
                "job_id": job.job_id,
                "title": job.title,
                "company": job.company,
                "content": cover_letters[job.job_id],
            }
            for job in jobs_to_apply
            if job.job_id in cover_letters
        ]
        agent_flow = _build_agent_flow(
            profile=profile,
            raw_jobs=raw_jobs,
            scored_jobs=scored_jobs,
            approved_jobs=approved_jobs,
            cover_letters=cover_letters,
            results=results,
            storage_target=storage_target,
        )

        return {
            "run_id": run_config.run_id,
            "status": "completed",
            "message": "Pipeline run completed.",
            "payload": {
                "profile": {
                    "goal": profile.goal,
                    "roles": profile.roles,
                    "locations": profile.locations,
                    "work_mode": profile.work_mode,
                    "min_salary": profile.min_salary,
                    "dry_run": profile.dry_run,
                },
                "counts": {
                    "raw_jobs": len(raw_jobs),
                    "scored_jobs": len(scored_jobs),
                    "approved_jobs": len(approved_jobs),
                    "applications_processed": applied_count,
                    "submission_target_successes": submission_target_successes,
                    "cover_letters_generated": len(cover_letters),
                },
                "runtime_inputs": {
                    "linkedin_email_provided": bool(linkedin_email.strip()),
                    "resume_uploaded": runtime_resume_path is not None,
                    "resume_file_name": _safe_resume_filename(resume_file_name) if runtime_resume_path else "",
                },
                "approved_jobs": [_job_to_dict(j) for j in approved_jobs],
                "cover_letters": cover_letter_entries,
                "agent_flow": agent_flow,
                "results": [_result_to_dict(r) for r in results],
                "tracking_backend": storage_target,
                "context_path": str(context_path),
                "timestamp": datetime.now().isoformat(timespec="seconds"),
            },
        }
    finally:
        config.LINKEDIN_EMAIL = original_email
        config.LINKEDIN_PASSWORD = original_password
        config.USER_RESUME_PATH = original_resume_path
        config.USE_TEMP_BROWSER_PROFILE = original_use_temp_browser_profile
        if runtime_resume_path is not None:
            try:
                runtime_resume_path.unlink(missing_ok=True)
            except Exception:
                pass





