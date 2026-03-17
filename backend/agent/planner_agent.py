"""
planner_agent.py
----------------
Planner builds search queries, scores jobs, and returns ranked candidates.
"""

import re
from dataclasses import dataclass

import config
from agent.base_agent import BaseAgent
from agent.manager_agent import SearchProfile


@dataclass
class JobListing:
    job_id: str
    platform: str
    title: str
    company: str
    location: str
    work_mode: str
    salary: str
    description: str
    url: str
    date_posted: str
    confidence_score: int = 0
    cover_letter_hint: str = ""
    already_applied: bool = False


class PlannerAgent(BaseAgent):
    SYSTEM_PROMPT = (
        "You are a career strategy AI. Evaluate job postings against candidate profile. "
        "Be strict about role family alignment and return JSON only."
    )

    def __init__(self, run_config=None):
        super().__init__("PlannerAgent", run_config=run_config)
        self.top_n_fallback = 3

    def _query_keywords_for_role(self, role: str, profile: SearchProfile) -> list[str]:
        role_lower = role.lower()
        keywords = list(profile.extra_keywords)

        if "machine learning" in role_lower or role_lower.startswith("ml "):
            keywords.extend(["machine learning", "ml", "mlops", "model deployment"])
        elif "generative ai" in role_lower or "gen ai" in role_lower:
            keywords.extend(["generative ai", "llm", "rag", "agentic ai"])
        elif "ai engineer" in role_lower:
            keywords.extend(["artificial intelligence", "ai", "llm"])
        elif "data scientist" in role_lower:
            keywords.extend(["data science", "statistics", "experimentation"])
        elif "data engineer" in role_lower:
            keywords.extend(["etl", "pipeline", "spark", "databricks"])

        deduped: list[str] = []
        seen = set()
        for keyword in keywords:
            normalised = re.sub(r"\s+", " ", keyword.strip().lower())
            if normalised and normalised not in seen:
                seen.add(normalised)
                deduped.append(keyword.strip())
        return deduped

    def build_search_queries(self, profile: SearchProfile) -> list[dict]:
        queries = []
        for platform in ["linkedin"]:
            for role in profile.roles:
                for location in profile.locations:
                    queries.append(
                        {
                            "platform": platform,
                            "role": role,
                            "location": location,
                            "keywords": self._query_keywords_for_role(role, profile),
                        }
                    )
        self.log.info(f"Built {len(queries)} search queries.")
        return queries

    def _family_aliases(self, role: str) -> set[str]:
        role_lower = role.lower()
        aliases = {role_lower}
        if "machine learning engineer" in role_lower or role_lower.startswith("ml engineer"):
            aliases |= {"machine learning engineer", "ml engineer", "mlops", "model deployment"}
        if "generative ai" in role_lower or "gen ai" in role_lower:
            aliases |= {"generative ai", "gen ai", "llm", "rag", "agentic"}
        if "ai engineer" in role_lower:
            aliases |= {"ai engineer", "artificial intelligence engineer", "ai", "llm"}
        if "data scientist" in role_lower:
            aliases |= {"data scientist", "applied scientist", "machine learning scientist"}
        if "data engineer" in role_lower:
            aliases |= {"data engineer", "etl", "pipeline", "spark", "databricks"}
        return aliases

    def _heuristic_score(self, job: JobListing, profile: SearchProfile) -> int:
        text = f"{job.title} {job.description} {job.company}".lower()
        title = (job.title or "").lower()
        score = 10

        best_role_hit = 0
        for role in profile.roles:
            role_score = 0
            aliases = self._family_aliases(role)
            for alias in aliases:
                if alias in title:
                    role_score += 30
                elif alias in text:
                    role_score += 12
            if role.lower() in title:
                role_score += 20
            if role.lower() in text:
                role_score += 10
            best_role_hit = max(best_role_hit, role_score)

        score += min(best_role_hit, 60)

        if profile.locations:
            target_locations = [loc.lower() for loc in profile.locations]
            loc_text = (job.location or "").lower()
            if any(loc in loc_text for loc in target_locations):
                score += 12
            elif "remote" in loc_text and any("remote" in loc for loc in target_locations):
                score += 12
            elif not loc_text:
                score += 4

        if profile.work_mode in {"remote", "onsite", "hybrid"}:
            if profile.work_mode == (job.work_mode or "").lower():
                score += 8

        kw_hits = 0
        for kw in profile.extra_keywords:
            if kw.lower() in text:
                kw_hits += 1
        score += min(kw_hits * 4, 12)

        if job.description:
            score += 8

        return max(0, min(100, score))

    def _default_cover_letter_hint(self, job: JobListing, profile: SearchProfile) -> str:
        points = []
        if profile.roles:
            points.append(f"Role alignment with {profile.roles[0]}")
        if job.work_mode and job.work_mode != "unknown":
            points.append(f"Fit for {job.work_mode} working style")
        if profile.extra_keywords:
            points.append(f"Experience in {', '.join(profile.extra_keywords[:3])}")
        if not points:
            points = ["Core technical match", "Relevant project impact", "Ability to deliver quickly"]
        return ", ".join(points[:3])

    def score_job(self, job: JobListing, profile: SearchProfile) -> JobListing:
        prompt = f"""
Candidate Profile:
- Target Roles: {profile.roles}
- Target Locations: {profile.locations}
- Preferred Work Mode: {profile.work_mode}
- Minimum Salary: {profile.min_salary} LPA
- Extra Keywords: {profile.extra_keywords}

Job Posting:
- Title: {job.title}
- Company: {job.company}
- Location: {job.location}
- Work Mode: {job.work_mode}
- Salary: {job.salary}
- Description (first 1200 chars):
{(job.description or '')[:1200]}

Return JSON only:
{{
  "confidence_score": <integer 0-100>,
  "cover_letter_hint": "<comma-separated talking points>"
}}
"""

        heuristic_score = self._heuristic_score(job, profile)
        result = self.ask_llm_json(prompt, system=self.SYSTEM_PROMPT)

        raw_score = int(result.get("confidence_score", 0) or 0)
        if raw_score <= 0:
            final_score = heuristic_score
        else:
            # Keep model score as primary signal; only rescue clearly bad low scores.
            final_score = raw_score
            if raw_score < 40 < heuristic_score:
                final_score = heuristic_score
            elif (not job.description) and heuristic_score > raw_score:
                final_score = round((raw_score * 0.7) + (heuristic_score * 0.3))

        final_score = max(0, min(100, final_score))
        job.confidence_score = final_score

        hint = str(result.get("cover_letter_hint", "") or "").strip()
        job.cover_letter_hint = hint if hint else self._default_cover_letter_hint(job, profile)

        self.log.info(
            f"Scored '{job.title}' @ {job.company} -> {job.confidence_score}/100 "
            f"(heuristic={heuristic_score}, llm={raw_score})"
        )
        return job

    def filter_jobs(self, jobs: list[JobListing], profile: SearchProfile, applied_ids: set[str]) -> list[JobListing]:
        filtered = []
        for job in jobs:
            if job.job_id in applied_ids:
                self.log.debug(f"Skip (already applied): {job.job_id}")
                job.already_applied = True
                continue
            if job.confidence_score < profile.min_confidence_score:
                self.log.debug(f"Skip (low score {job.confidence_score}): {job.title}")
                continue
            filtered.append(job)

        filtered.sort(key=lambda j: j.confidence_score, reverse=True)
        if not filtered:
            eligible = [j for j in jobs if j.job_id not in applied_ids]
            eligible.sort(key=lambda j: j.confidence_score, reverse=True)
            fallback = eligible[: self.top_n_fallback]
            if fallback:
                self.log.info(
                    f"No jobs passed threshold {profile.min_confidence_score}; "
                    f"using top-{len(fallback)} fallback for Critic review."
                )
                return fallback

        self.log.info(f"{len(filtered)} jobs passed filter (min score={profile.min_confidence_score}).")
        return filtered

    def run(self, profile: SearchProfile, raw_jobs: list[JobListing], applied_ids: set[str]) -> list[JobListing]:
        self.log.info(f"Planner received {len(raw_jobs)} raw job listings to score.")
        scored = [self.score_job(job, profile) for job in raw_jobs]
        final = self.filter_jobs(scored, profile, applied_ids)
        self.log.info(f"Planner returning {len(final)} jobs for review.")
        return final

