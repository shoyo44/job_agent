from pathlib import Path
import shutil

import config
from agent.submission_agent import ApplicationResult, SubmitResult
from agent.planner_agent import JobListing
from agent.tracker_agent import TrackerAgent


def _job(job_id: str) -> JobListing:
    return JobListing(
        job_id=job_id,
        platform="linkedin",
        title="AI Engineer",
        company="Example",
        location="Remote",
        work_mode="remote",
        salary="Not specified",
        description="desc",
        url="https://example.com/job",
        date_posted="2026-03-15",
    )


def test_tracker_records_and_deduplicates(monkeypatch):
    test_dir = Path("data/test_tmp_tracker")
    if test_dir.exists():
        shutil.rmtree(test_dir)
    test_dir.mkdir(parents=True, exist_ok=True)

    excel_path = test_dir / "list.xlsx"
    monkeypatch.setattr(config, "EXCEL_FILE_PATH", Path(excel_path))
    monkeypatch.setattr(config, "MONGODB_URI", "")

    tracker = TrackerAgent()
    r1 = ApplicationResult(job=_job("job-1"), result=SubmitResult.APPLIED, notes="ok")

    tracker.record_results([r1])
    tracker.record_results([r1])

    ids = tracker.get_applied_ids()
    assert ids == {"job-1"}
