"""
critic_agent.py
---------------
Final quality-control layer between Planner and Submission.
"""

from dataclasses import dataclass

from agent.base_agent import BaseAgent
from agent.manager_agent import SearchProfile
from agent.planner_agent import JobListing


@dataclass
class CriticDecision:
    job: JobListing
    approved: bool
    reason: str
    adjusted_score: int


class CriticAgent(BaseAgent):
    SYSTEM_PROMPT = (
        "You are a smart job application reviewer. "
        "Make APPROVE/SKIP decisions on job listings for a candidate. "
        "Be strict about role-family mismatches and return JSON only."
    )

    def __init__(self, run_config=None):
        super().__init__("CriticAgent", run_config=run_config)
        self.max_finalists = 3

    def review_job(self, job: JobListing, profile: SearchProfile) -> CriticDecision:
        prompt = f"""
Candidate Profile:
- Target Roles: {profile.roles}
- Target Locations: {profile.locations}
- Preferred Work Mode: {profile.work_mode}
- Minimum Salary: {profile.min_salary} LPA

Job Listing:
- Title: {job.title}
- Company: {job.company}
- Location: {job.location}
- Work Mode: {job.work_mode}
- Salary: {job.salary}
- Planner Score: {job.confidence_score}/100
- Description (first 1200 chars):
{(job.description or '')[:1200]}

Return JSON only:
{{
  "approved": true or false,
  "adjusted_score": <integer 0-100>,
  "reason": "<brief reason>"
}}
"""

        result = self.ask_llm_json(prompt, system=self.SYSTEM_PROMPT)

        if not result:
            approved = job.confidence_score >= max(profile.min_confidence_score - 5, 55)
            adjusted_score = job.confidence_score
            reason = "Critic fallback: used planner score because LLM output was invalid."
        else:
            approved = bool(result.get("approved", False))
            adjusted_score = int(result.get("adjusted_score", job.confidence_score) or job.confidence_score)
            adjusted_score = max(0, min(100, adjusted_score))
            reason = str(result.get("reason", "No reason provided."))

        status = "APPROVED" if approved else "SKIPPED"
        self.log.info(
            f"{status} | '{job.title}' @ {job.company} "
            f"| Score: {job.confidence_score}->{adjusted_score} "
            f"| Reason: {reason}"
        )

        job.confidence_score = adjusted_score

        return CriticDecision(
            job=job,
            approved=approved,
            reason=reason,
            adjusted_score=adjusted_score,
        )

    def run(self, jobs: list[JobListing], profile: SearchProfile) -> list[JobListing]:
        self.log.info(f"Critic reviewing {len(jobs)} job listings...")
        decisions: list[CriticDecision] = []

        for job in jobs:
            decisions.append(self.review_job(job, profile))
            self.human_pause(0.5)

        approved_jobs = [d.job for d in decisions if d.approved]

        decisions.sort(key=lambda d: d.adjusted_score, reverse=True)
        if not approved_jobs and decisions:
            self.log.info("No jobs approved by Critic. Falling back to highest scored jobs.")
            approved_jobs = [d.job for d in decisions[: self.max_finalists]]
        else:
            approved_jobs.sort(key=lambda job: job.confidence_score, reverse=True)
            approved_jobs = approved_jobs[: self.max_finalists]

        self.log.info(f"Critic selected {len(approved_jobs)}/{len(jobs)} jobs for submission.")
        return approved_jobs
