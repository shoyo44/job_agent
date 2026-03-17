"""
run_config.py
-------------
Runtime-scoped settings passed through the pipeline to avoid mutating
global config module state.
"""

from dataclasses import dataclass
from datetime import datetime

import config


@dataclass(frozen=True)
class RunConfig:
    """Execution-scoped settings for a single pipeline run."""

    run_id: str
    dry_run: bool
    max_scraped_jobs: int
    max_scoring_jobs: int
    max_applications: int
    max_approved_candidates: int

    @classmethod
    def build(
        cls,
        *,
        dry_run_override: bool,
        max_scraped_jobs: int,
        max_scoring_jobs: int,
        max_applications: int,
        max_approved_candidates: int,
    ) -> "RunConfig":
        now = datetime.now().strftime("%Y%m%d-%H%M%S")
        return cls(
            run_id=f"run-{now}",
            dry_run=(dry_run_override or config.DRY_RUN),
            max_scraped_jobs=max_scraped_jobs,
            max_scoring_jobs=max_scoring_jobs,
            max_applications=max_applications,
            max_approved_candidates=max_approved_candidates,
        )
