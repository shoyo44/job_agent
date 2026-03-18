import os
import shutil
from pathlib import Path

from agent.manager_agent import SearchProfile
from agent.planner_agent import JobListing
from agent.submission_agent import ApplicationResult, SubmitResult
from api import service


def _job(job_id: str = "job-100", title: str = "AI Engineer", company: str = "Example") -> JobListing:
    return JobListing(
        job_id=job_id,
        platform="linkedin",
        title=title,
        company=company,
        location="Remote",
        work_mode="remote",
        salary="Not specified",
        description="desc",
        url=f"https://example.com/{job_id}",
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


def test_execute_pipeline_returns_submission_payload_contract(monkeypatch):
    jobs = [_job("job-100", "AI Engineer", "Example"), _job("job-200", "ML Engineer", "OtherCo")]
    test_dir = Path("data/test_tmp_submission_payload")
    if test_dir.exists():
        shutil.rmtree(test_dir)
    test_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(service.ManagerAgent, "build_profile_from_config", lambda self: _profile())
    monkeypatch.setattr(
        service.PlannerAgent,
        "build_search_queries",
        lambda self, profile: [{"platform": "linkedin", "role": "AI Engineer", "location": "Remote", "keywords": []}],
    )
    monkeypatch.setattr(service, "run_scrapers", lambda *args, **kwargs: jobs)
    monkeypatch.setattr(service.PlannerAgent, "run", lambda self, profile, raw_jobs, applied_ids: raw_jobs)
    monkeypatch.setattr(service.CriticAgent, "run", lambda self, scored_jobs, profile: scored_jobs)
    monkeypatch.setattr(service.TrackerAgent, "get_applied_ids", lambda self: set())
    monkeypatch.setattr(service.TrackerAgent, "run", lambda self, results: None)
    monkeypatch.setattr(service, "extract_skills", lambda *_: ["python"])
    monkeypatch.setattr(service, "summarise_resume", lambda *args, **kwargs: "Resume summary")
    monkeypatch.setattr(service, "append_jsonl", lambda *args, **kwargs: None)
    monkeypatch.setattr(service.CoverLetterAgent, "generate", lambda self, job, resume_text: f"Letter for {job.title}")

    def fake_submission_run(self, jobs_to_apply, cover_letters, resume_summary="", applied_ids=None):
        return [
            ApplicationResult(job=jobs_to_apply[0], result=SubmitResult.DRY_RUN, notes="dry"),
            ApplicationResult(job=jobs_to_apply[1], result=SubmitResult.SKIPPED, notes="already applied"),
        ]

    monkeypatch.setattr(service.SubmissionAgent, "run", fake_submission_run)

    old_cwd = os.getcwd()
    try:
        os.chdir(test_dir)
        outcome = service.execute_pipeline(
            goal="",
            config_only=True,
            dry_run=True,
            easy_apply_only=True,
            max_scraped_jobs=10,
            max_scoring_jobs=5,
            max_applications=1,
            submission_target_successes=1,
            max_approved_candidates=3,
        )
    finally:
        os.chdir(old_cwd)

    assert outcome["status"] == "completed"
    payload = outcome["payload"]

    assert payload["counts"]["approved_jobs"] == 2
    assert payload["counts"]["applications_processed"] == 1
    assert payload["counts"]["cover_letters_generated"] == 2

    assert payload["submission_plan"]["target_successes"] == 1
    assert payload["submission_plan"]["jobs_to_try"] == 2
    assert len(payload["submission_plan"]["finalists"]) == 2

    assert len(payload["results"]) == 2
    assert payload["results"][0]["result"] == "DryRun"
    assert payload["results"][1]["result"] == "Skipped"
    assert payload["results"][0]["job"]["title"] == "AI Engineer"
    assert payload["cover_letters"][0]["content"] == "Letter for AI Engineer"
