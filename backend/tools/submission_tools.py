from __future__ import annotations

from pathlib import Path
from typing import Any


def ensure_runtime_browser_profile(*, base_dir: str | Path, run_id: str) -> Path:
    """Create and return a shared run-scoped browser profile directory."""
    root = Path(base_dir)
    profile_dir = root / run_id
    profile_dir.mkdir(parents=True, exist_ok=True)
    return profile_dir


def build_submission_plan(
    *,
    approved_jobs: list[Any],
    submission_target_successes: int,
) -> dict[str, Any]:
    """Return a frontend/backend-friendly submission plan summary."""
    finalists = approved_jobs[:3]
    return {
        "target_successes": max(1, submission_target_successes),
        "jobs_to_try": len(finalists),
        "finalists": [
            {
                "job_id": getattr(job, "job_id", ""),
                "title": getattr(job, "title", ""),
                "company": getattr(job, "company", ""),
                "platform": getattr(job, "platform", ""),
                "location": getattr(job, "location", ""),
                "confidence_score": getattr(job, "confidence_score", 0),
            }
            for job in finalists
        ],
    }


def format_submission_log(plan: dict[str, Any]) -> str:
    """Format a concise log message for submission handoff debugging."""
    finalists = plan.get("finalists") or []
    labels = [
        f"{item.get('title', 'Unknown role')} @ {item.get('company', 'Unknown company')}"
        for item in finalists
    ]
    return (
        f"Submission plan | target_successes={plan.get('target_successes', 1)} "
        f"| jobs_to_try={plan.get('jobs_to_try', 0)} "
        f"| finalists={labels}"
    )
