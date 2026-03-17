"""
main.py
-------
Main orchestrator for the Job Application Agent System.
"""

import argparse
import logging
from pathlib import Path

import config
from agent.critic_agent import CriticAgent
from agent.errors import AgentError, ScraperError
from agent.manager_agent import ManagerAgent
from agent.planner_agent import JobListing, PlannerAgent
from agent.run_config import RunConfig
from agent.submission_agent import SubmissionAgent
from agent.tracker_agent import TrackerAgent
from tools.agent_jsonl import append_jsonl
from tools.cover_letter import CoverLetterAgent
from tools.resume_tools import extract_skills, summarise_resume
from tools.utils import deduplicate_jobs, format_table

MAX_SCRAPED_JOBS = 10
MAX_SCORING_JOBS = 10
MAX_APPLICATIONS = 3
MAX_APPROVED_CANDIDATES = 10
AGENT_CONTEXT_JSONL = Path("data") / "agent_context.jsonl"

log = logging.getLogger("main")


def print_runtime_warning(stage: str, error: Exception) -> None:
    """Print a concise runtime warning without a full traceback."""
    if isinstance(error, AgentError):
        print(f"[Main] {stage} failed: {error.code} - {error.message}")
    else:
        print(f"[Main] {stage} failed: {error}")


def prompt_yes_no(prompt: str, default: bool) -> bool:
    """Prompt for a yes/no answer with a default."""
    suffix = "Y/n" if default else "y/N"
    answer = input(f"{prompt} [{suffix}]: ").strip().lower()
    if not answer:
        return default
    return answer in {"y", "yes"}


def parse_args():
    parser = argparse.ArgumentParser(description="Job Application Agent System")
    parser.add_argument(
        "--goal",
        type=str,
        default="",
        help='Natural language job goal, e.g. "Apply for AI jobs in Bangalore"',
    )
    parser.add_argument(
        "--config-only",
        action="store_true",
        help="Skip LLM goal parsing, use .env defaults directly",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Override DRY_RUN to True (do NOT submit applications)",
    )
    return parser.parse_args()


def run_scrapers(
    queries: list[dict],
    run_config: RunConfig,
    max_total_jobs: int,
) -> list[JobListing]:
    """Runs the LinkedIn scraper and caps the total collected jobs."""
    from web_scrapping.linkedin_playwrite import LinkedInPlaywrightScraper

    all_jobs: list[JobListing] = []
    seen_ids: set[str] = set()

    def _add_jobs(new_jobs: list) -> None:
        unique = deduplicate_jobs(new_jobs, seen_ids)
        all_jobs.extend(unique)

    queries = [q for q in queries if q["platform"] == "linkedin"]
    if not queries:
        return all_jobs

    li_scraper = LinkedInPlaywrightScraper(run_id=run_config.run_id)
    try:
        li_scraper.start()
        if not li_scraper.login():
            print("[Main] LinkedIn login failed - skipping LinkedIn.")
            return all_jobs

        # Seed pass: try to capture at least one relevant Easy Apply job early.
        # This gives the pipeline a higher chance of including a low-friction application.
        primary_query = queries[0]
        if max_total_jobs > 0:
            try:
                seed_jobs = li_scraper.search_jobs(
                    role=primary_query["role"],
                    location=primary_query["location"],
                    keywords=primary_query.get("keywords", []),
                    easy_apply_only=True,
                    max_pages=1,
                    max_days_old=primary_query.get("max_days_old", 30),
                    max_jobs=1,
                    enrich_details=False,
                )
                seed_jobs = [
                    j for j in seed_jobs
                    if li_scraper._is_relevant_title(
                        j.title,
                        primary_query["role"],
                        primary_query.get("keywords", []),
                    )
                ][:1]
                if seed_jobs:
                    _add_jobs(seed_jobs)
                    print(
                        f"[Main] Seeded {len(seed_jobs)} relevant Easy Apply job "
                        f"for {primary_query['role']} in {primary_query['location']}."
                    )
                else:
                    print(
                        f"[Main] Seed pass found no relevant Easy Apply jobs for "
                        f"{primary_query['role']} in {primary_query['location']}."
                    )
            except Exception as e:
                print_runtime_warning("LinkedIn seed Easy Apply pass", e)

        for query in queries:
            remaining_jobs = max_total_jobs - len(all_jobs)
            if remaining_jobs <= 0:
                print(f"[Main] Reached scrape limit of {max_total_jobs} jobs.")
                break

            try:
                requested_max = min(query.get("max_jobs", max_total_jobs), remaining_jobs)
                jobs = li_scraper.search_jobs(
                    role=query["role"],
                    location=query["location"],
                    keywords=query.get("keywords", []),
                    # Enforce Easy Apply for all collected jobs.
                    easy_apply_only=True,
                    max_pages=query.get("max_pages", 3),
                    max_days_old=query.get("max_days_old", 30),
                    max_jobs=requested_max,
                    enrich_details=query.get("enrich_details", False),
                )

                # Fallback pass 2: if recall is still too low, run a relaxed broad pass and merge.
                if len(jobs) < min(2, requested_max):
                    relaxed_jobs = li_scraper.search_jobs(
                        role=query["role"],
                        location=query["location"],
                        keywords=[],
                        easy_apply_only=True,
                        max_pages=query.get("max_pages", 3),
                        max_days_old=max(query.get("max_days_old", 30), 45),
                        max_jobs=requested_max,
                        enrich_details=False,
                    )
                    existing_ids = {j.job_id for j in jobs}
                    for candidate in relaxed_jobs:
                        if candidate.job_id in existing_ids:
                            continue
                        jobs.append(candidate)
                        existing_ids.add(candidate.job_id)
                        if len(jobs) >= requested_max:
                            break

                strict_jobs = [
                    j for j in jobs[:requested_max]
                    if li_scraper._is_relevant_title(j.title, query["role"], query.get("keywords", []))
                ]
                dropped_strict = len(jobs[:requested_max]) - len(strict_jobs)
                if dropped_strict > 0:
                    print(f"[Main] Dropped {dropped_strict} low-relevance jobs for role {query['role']}")
                _add_jobs(strict_jobs)
                print(
                    f"[Main] LinkedIn scraped {len(jobs)} raw / {len(all_jobs)} total unique "
                    f"- {query['role']} in {query['location']}"
                )
            except ScraperError as e:
                print_runtime_warning(
                    f"LinkedIn query ({query['role']} / {query['location']})",
                    e,
                )
            except Exception as e:
                print_runtime_warning(
                    f"LinkedIn query ({query['role']} / {query['location']})",
                    e,
                )
    except ScraperError:
        raise
    except Exception as e:
        raise ScraperError(
            stage="run_scrapers",
            code="linkedin_runtime_failure",
            message=str(e),
            retriable=True,
            details={"run_id": run_config.run_id},
        ) from e
    finally:
        try:
            li_scraper.stop()
        except Exception:
            pass

    return all_jobs


def print_summary_table(jobs: list[JobListing]) -> None:
    if not jobs:
        print("No jobs to display.")
        return
    headers = ["Title", "Company", "Platform", "Location", "Score"]
    rows = [
        [j.title[:30], j.company[:25], j.platform, j.location[:20], str(j.confidence_score)]
        for j in jobs
    ]
    print("\n" + format_table(headers, rows))


def main():
    args = parse_args()

    run_config = RunConfig.build(
        dry_run_override=args.dry_run,
        max_scraped_jobs=MAX_SCRAPED_JOBS,
        max_scoring_jobs=MAX_SCORING_JOBS,
        max_applications=MAX_APPLICATIONS,
        max_approved_candidates=MAX_APPROVED_CANDIDATES,
    )

    AGENT_CONTEXT_JSONL.parent.mkdir(parents=True, exist_ok=True)
    AGENT_CONTEXT_JSONL.write_text("", encoding="utf-8")

    if run_config.dry_run:
        print("[Main] DRY RUN mode enabled - applications will NOT be submitted.")

    print("=" * 60)
    print("    Job Application Agent System - Starting")
    print(f"    Run ID: {run_config.run_id}")
    print("=" * 60)

    easy_apply_only = True
    if not args.config_only and not args.goal.strip():
        role = input("What kind of jobs should I apply for? ").strip()
        location = input("Preferred location (blank for config/default): ").strip()
        work_mode = input("Preferred work mode (any/remote/onsite/hybrid): ").strip().lower()
        interactive_dry_run = prompt_yes_no("Run in dry-run mode?", run_config.dry_run)
        easy_apply_only = prompt_yes_no("Only search for Easy Apply jobs?", True)

        goal_parts = [role] if role else []
        if location:
            goal_parts.append(f"in {location}")
        if work_mode in {"remote", "onsite", "hybrid"}:
            goal_parts.append(work_mode)
        if easy_apply_only:
            goal_parts.append("easy apply only")
        args.goal = " ".join(goal_parts).strip()

        if interactive_dry_run != run_config.dry_run:
            run_config = RunConfig(
                run_id=run_config.run_id,
                dry_run=interactive_dry_run,
                max_scraped_jobs=run_config.max_scraped_jobs,
                max_scoring_jobs=run_config.max_scoring_jobs,
                max_applications=run_config.max_applications,
                max_approved_candidates=run_config.max_approved_candidates,
            )

    manager = ManagerAgent(run_config=run_config)
    try:
        if args.config_only or not args.goal:
            profile = manager.build_profile_from_config()
        else:
            profile = manager.run(args.goal)
    except Exception as e:
        print_runtime_warning("Goal parsing with Cloudflare AI", e)
        print("[Main] Falling back to config-based profile.")
        profile = manager.build_profile_from_config()

    profile.dry_run = run_config.dry_run

    print(f"\n[Main] Goal: {profile.goal}")
    print(f"[Main] Roles: {profile.roles}")
    print(f"[Main] Locations: {profile.locations}")
    print(f"[Main] DRY RUN: {profile.dry_run}\n")
    append_jsonl(
        AGENT_CONTEXT_JSONL,
        "search_profile",
        {
            "goal": profile.goal,
            "profile": profile,
            "run_id": run_config.run_id,
        },
    )

    planner = PlannerAgent(run_config=run_config)
    queries = planner.build_search_queries(profile)
    for query in queries:
        query["easy_apply_only"] = easy_apply_only
        query["max_jobs"] = run_config.max_scraped_jobs

    append_jsonl(
        AGENT_CONTEXT_JSONL,
        "search_queries",
        {"queries": queries, "run_id": run_config.run_id},
    )

    tracker = TrackerAgent(run_config=run_config)
    applied_ids = tracker.get_applied_ids()

    print("[Main] Starting web scrapers...")
    try:
        raw_jobs = run_scrapers(
            queries,
            run_config=run_config,
            max_total_jobs=run_config.max_scraped_jobs,
        )
    except Exception as e:
        print_runtime_warning("Web scraping", e)
        raw_jobs = []

    print(f"[Main] Total raw jobs collected: {len(raw_jobs)} / {run_config.max_scraped_jobs}")
    append_jsonl(
        AGENT_CONTEXT_JSONL,
        "raw_jobs",
        {"count": len(raw_jobs), "jobs": raw_jobs, "run_id": run_config.run_id},
    )

    raw_jobs = raw_jobs[: run_config.max_scoring_jobs]
    print(
        f"[Main] Keeping {len(raw_jobs)} jobs for scoring "
        f"(limit {run_config.max_scoring_jobs})."
    )
    append_jsonl(
        AGENT_CONTEXT_JSONL,
        "shortlisted_jobs",
        {"count": len(raw_jobs), "jobs": raw_jobs, "run_id": run_config.run_id},
    )

    if not raw_jobs:
        print("[Main] No jobs found. Check scraper connectivity and credentials.")
        return

    try:
        scored_jobs = planner.run(profile, raw_jobs, applied_ids)
    except Exception as e:
        print_runtime_warning("Job scoring", e)
        print("[Main] Could not score jobs because the LLM is unavailable.")
        return

    print(f"[Main] Jobs after scoring & filtering: {len(scored_jobs)}")
    append_jsonl(
        AGENT_CONTEXT_JSONL,
        "scored_jobs",
        {"count": len(scored_jobs), "jobs": scored_jobs, "run_id": run_config.run_id},
    )

    if not scored_jobs:
        print("[Main] No jobs met the minimum confidence score. Done.")
        return

    critic = CriticAgent(run_config=run_config)
    try:
        approved_jobs = critic.run(scored_jobs, profile)
    except Exception as e:
        print_runtime_warning("Critic review", e)
        print("[Main] Could not complete final approval because the LLM is unavailable.")
        return

    approved_jobs = approved_jobs[: max(10, run_config.max_approved_candidates)]
    append_jsonl(
        AGENT_CONTEXT_JSONL,
        "approved_jobs",
        {"count": len(approved_jobs), "jobs": approved_jobs, "run_id": run_config.run_id},
    )

    print(f"\n[Main] Critic approved {len(approved_jobs)} jobs:")
    print_summary_table(approved_jobs)

    if not approved_jobs:
        print("[Main] All jobs were rejected by the Critic. Done.")
        return

    resume_skills = extract_skills(config.USER_RESUME_PATH)
    try:
        resume_text = summarise_resume(
            config.USER_RESUME_PATH,
            llm_caller=CoverLetterAgent(run_config=run_config).ask_llm,
        )
    except Exception as e:
        print_runtime_warning("Resume summarisation", e)
        resume_text = summarise_resume(config.USER_RESUME_PATH)

    if resume_skills:
        resume_text = f"{resume_text}\n\nRelevant skills: {', '.join(resume_skills[:20])}"

    # Hierarchical fallback: keep trying next approved job until one application succeeds.
    submission_target_successes = 1
    jobs_to_apply = approved_jobs
    cover_letter_agent = CoverLetterAgent(run_config=run_config)
    cover_letters: dict[str, str] = {}
    for job in jobs_to_apply:
        try:
            generated = cover_letter_agent.generate(job, resume_text).strip()
            if generated:
                cover_letters[job.job_id] = generated
        except Exception as e:
            print_runtime_warning(
                f"Cover letter generation ({job.title} @ {job.company})",
                e,
            )

    append_jsonl(
        AGENT_CONTEXT_JSONL,
        "resume_context",
        {
            "resume_summary": resume_text,
            "resume_skills": resume_skills[:20],
            "cover_letters_generated": len(cover_letters),
            "run_id": run_config.run_id,
        },
    )

    submission_run_config = RunConfig(
        run_id=run_config.run_id,
        dry_run=run_config.dry_run,
        max_scraped_jobs=run_config.max_scraped_jobs,
        max_scoring_jobs=run_config.max_scoring_jobs,
        max_applications=submission_target_successes,
        max_approved_candidates=run_config.max_approved_candidates,
    )
    print(
        f"[Main] Submission fallback mode: will try approved jobs in order until "
        f"{submission_target_successes} success."
    )
    submission = SubmissionAgent(run_config=submission_run_config)
    try:
        results = submission.run(
            jobs_to_apply,
            cover_letters,
            resume_summary=resume_text,
            applied_ids=applied_ids,
        )
    except Exception as e:
        print_runtime_warning("Submission", e)
        print("[Main] No applications were submitted.")
        return

    append_jsonl(
        AGENT_CONTEXT_JSONL,
        "submission_results",
        {"results": results, "run_id": run_config.run_id},
    )

    try:
        tracker.run(results)
    except Exception as e:
        print_runtime_warning("Tracking update", e)
        print("[Main] Applications ran, but results could not be written to the tracker.")
        return

    applied_count = sum(1 for r in results if r.result.value in ("Applied", "DryRun"))
    storage_target = (
        f"MongoDB: {config.MONGODB_DB}.{config.MONGODB_COLLECTION}"
        if tracker.use_mongodb
        else f"Excel: {config.EXCEL_FILE_PATH}"
    )
    print("\n" + "=" * 60)
    print(f"    Run Complete - {applied_count} applications processed")
    print(f"    Tracking backend: {storage_target}")
    print(f"    Agent context JSONL: {AGENT_CONTEXT_JSONL}")
    print(f"    Run ID: {run_config.run_id}")
    print("=" * 60)


if __name__ == "__main__":
    main()






