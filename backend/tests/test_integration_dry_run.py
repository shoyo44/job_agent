import argparse
from pathlib import Path
import shutil

import main
from agent.manager_agent import SearchProfile
from agent.planner_agent import JobListing
from agent.submission_agent import ApplicationResult, SubmitResult


def _job() -> JobListing:
    return JobListing(
        job_id="job-100",
        platform="linkedin",
        title="AI Engineer",
        company="Example",
        location="Remote",
        work_mode="remote",
        salary="Not specified",
        description="desc",
        url="https://example.com/job",
        date_posted="2026-03-15",
        confidence_score=90,
    )


def _profile() -> SearchProfile:
    return SearchProfile(
        goal="Configured",
        roles=["AI Engineer"],
        locations=["Remote"],
        work_mode="remote",
        min_salary=0,
        min_confidence_score=60,
        max_applications=3,
        dry_run=True,
        extra_keywords=[],
    )


def test_main_dry_run_integration(monkeypatch):
    test_dir = Path("data/test_tmp_integration")
    if test_dir.exists():
        shutil.rmtree(test_dir)
    test_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(main, "AGENT_CONTEXT_JSONL", test_dir / "agent_context.jsonl")
    monkeypatch.setattr(
        main,
        "parse_args",
        lambda: argparse.Namespace(goal="", config_only=True, dry_run=True),
    )

    monkeypatch.setattr(main.ManagerAgent, "build_profile_from_config", lambda self: _profile())
    monkeypatch.setattr(main.PlannerAgent, "build_search_queries", lambda self, profile: [{"platform": "linkedin", "role": "AI Engineer", "location": "Remote", "keywords": []}])
    monkeypatch.setattr(main, "run_scrapers", lambda *args, **kwargs: [_job()])
    monkeypatch.setattr(main.PlannerAgent, "run", lambda self, profile, raw_jobs, applied_ids: raw_jobs)
    monkeypatch.setattr(main.CriticAgent, "run", lambda self, jobs, profile: jobs)
    monkeypatch.setattr(main.TrackerAgent, "get_applied_ids", lambda self: set())
    monkeypatch.setattr(main.TrackerAgent, "run", lambda self, results: None)
    monkeypatch.setattr(main, "extract_skills", lambda *_: ["python"])
    monkeypatch.setattr(main, "summarise_resume", lambda *args, **kwargs: "Resume summary")
    monkeypatch.setattr(main, "append_jsonl", lambda *args, **kwargs: None)

    captured = {}

    def fake_submission_run(self, jobs, cover_letters, resume_summary="", applied_ids=None):
        captured["count"] = len(jobs)
        return [ApplicationResult(job=jobs[0], result=SubmitResult.DRY_RUN, notes="dry")]

    monkeypatch.setattr(main.SubmissionAgent, "run", fake_submission_run)

    main.main()
    assert captured["count"] == 1
