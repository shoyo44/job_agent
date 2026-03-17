from agent.manager_agent import SearchProfile
from agent.planner_agent import JobListing, PlannerAgent


def _profile() -> SearchProfile:
    return SearchProfile(
        goal="test",
        roles=["AI Engineer"],
        locations=["Remote"],
        work_mode="remote",
        min_salary=0,
        min_confidence_score=70,
        max_applications=3,
        dry_run=True,
        extra_keywords=["llm"],
    )


def _job(job_id: str, title: str) -> JobListing:
    return JobListing(
        job_id=job_id,
        platform="linkedin",
        title=title,
        company="Example",
        location="Remote",
        work_mode="remote",
        salary="Not specified",
        description="We need AI and LLM engineering experience.",
        url="https://example.com/job",
        date_posted="2026-03-15",
    )


def test_planner_scores_and_filters(monkeypatch):
    planner = PlannerAgent()
    profile = _profile()
    jobs = [_job("a1", "AI Engineer"), _job("a2", "Data Engineer")]

    responses = iter([
        {"confidence_score": 92, "cover_letter_hint": "llm,python,deployment"},
        {"confidence_score": 55, "cover_letter_hint": "etl,pipelines,sql"},
    ])
    monkeypatch.setattr(planner, "ask_llm_json", lambda *args, **kwargs: next(responses))

    scored = planner.run(profile, jobs, applied_ids=set())
    assert len(scored) == 1
    assert scored[0].job_id == "a1"
    assert scored[0].confidence_score == 92


def test_planner_skips_already_applied(monkeypatch):
    planner = PlannerAgent()
    profile = _profile()
    job = _job("dup-1", "AI Engineer")
    monkeypatch.setattr(
        planner,
        "ask_llm_json",
        lambda *args, **kwargs: {"confidence_score": 95, "cover_letter_hint": "x"},
    )

    result = planner.run(profile, [job], applied_ids={"dup-1"})
    assert result == []
