"""
manager_agent.py
----------------
The Manager Agent serves as the entry point for a job search session.
"""

import re
from dataclasses import dataclass, field
from typing import Optional

import config
from agent.base_agent import BaseAgent


@dataclass
class SearchProfile:
    goal: str
    roles: list[str]
    locations: list[str]
    work_mode: str
    min_salary: int
    min_confidence_score: int
    max_applications: int
    dry_run: bool
    extra_keywords: list[str] = field(default_factory=list)


class ManagerAgent(BaseAgent):
    SYSTEM_PROMPT = (
        "You are an expert career advisor and job search coordinator. "
        "Extract structured search parameters from natural language and return JSON only."
    )

    def __init__(self, run_config=None):
        super().__init__("ManagerAgent", run_config=run_config)
        self.profile: Optional[SearchProfile] = None

    def _normalise_min_salary_lpa(self, value: int) -> int:
        if value <= 0:
            return 0
        # If model returns INR annual amount, convert to LPA.
        if value >= 100000:
            value = round(value / 100000)
        # Guard against unrealistic LPA values from hallucinated extraction.
        if value > 100:
            return config.USER_MIN_SALARY
        return max(0, min(value, 100))

    def _goal_mentions_salary(self, user_goal: str) -> bool:
        goal = user_goal.lower()
        salary_patterns = [
            r"\b\d+\s*lpa\b",
            r"\b\d+\s*(?:k|m)\b",
            r"\bsalary\b",
            r"\bctc\b",
            r"\bcompensation\b",
            r"\bpay\b",
        ]
        return any(re.search(p, goal) for p in salary_patterns)

    def _canonical_role(self, text: str) -> str:
        raw = re.sub(r"\s+", " ", text.strip().lower())
        mappings = {
            "ml engineer": "Machine Learning Engineer",
            "machine learning engineer": "Machine Learning Engineer",
            "ai engineer": "AI Engineer",
            "artificial intelligence engineer": "AI Engineer",
            "gen ai engineer": "Generative AI Engineer",
            "generative ai engineer": "Generative AI Engineer",
            "data scientist": "Data Scientist",
            "data engineer": "Data Engineer",
            "ai researcher": "AI Researcher",
            "ml researcher": "AI Researcher",
            "machine learning researcher": "AI Researcher",
        }
        return mappings.get(raw, raw.title())

    def _normalise_work_mode(self, value: str) -> str:
        v = (value or "").strip().lower()
        if v in {"remote", "onsite", "hybrid", "any"}:
            return v
        return "any"

    def _infer_roles_from_goal(self, user_goal: str) -> list[str]:
        goal = user_goal.lower()
        role_aliases = [
            ("Machine Learning Engineer", ["machine learning engineer", "ml engineer", "ml eng"]),
            ("AI Engineer", ["ai engineer", "artificial intelligence engineer"]),
            ("Generative AI Engineer", ["gen ai engineer", "generative ai engineer", "llm engineer"]),
            ("Data Scientist", ["data scientist"]),
            ("AI Researcher", ["ai researcher", "ml researcher", "machine learning researcher"]),
            ("Data Engineer", ["data engineer"]),
        ]
        matched_roles = []
        for canonical_role, aliases in role_aliases:
            if any(alias in goal for alias in aliases):
                matched_roles.append(canonical_role)

        if matched_roles:
            return matched_roles

        cleaned_goal = re.sub(r"\beasy apply only\b", "", goal)
        cleaned_goal = re.sub(r"\b(remote|onsite|hybrid)\b", "", cleaned_goal)
        cleaned_goal = re.sub(r"\bin\s+[a-z\s]+\b", "", cleaned_goal)
        cleaned_goal = re.sub(r"\b(apply|jobs?|for|all|only|prefer|find|search)\b", "", cleaned_goal)
        cleaned_goal = " ".join(cleaned_goal.split()).strip(" ,.-")
        if cleaned_goal:
            return [cleaned_goal.title()]

        return config.USER_TARGET_ROLES

    def _infer_locations_from_goal(self, user_goal: str) -> list[str]:
        goal = user_goal.strip()
        matches = re.findall(
            r"\bin\s+([a-zA-Z\s]+?)(?=\s+(?:remote|onsite|hybrid|easy apply|with|salary|jobs?)\b|$)",
            goal,
            flags=re.IGNORECASE,
        )
        locations = []
        for match in matches:
            location = " ".join(match.split()).strip(" ,.-")
            if location:
                locations.append(location.title())

        lowered = user_goal.lower()
        if "remote" in lowered and "Remote" not in locations:
            locations.append("Remote")

        return locations or config.USER_TARGET_LOCATIONS

    def _fallback_profile_fields(self, user_goal: str) -> dict:
        lowered = user_goal.lower()
        work_mode = config.USER_WORK_MODE
        if "remote" in lowered:
            work_mode = "remote"
        elif "hybrid" in lowered:
            work_mode = "hybrid"
        elif "onsite" in lowered:
            work_mode = "onsite"

        salary_match = re.search(r"(\d+)\s*lpa", lowered)
        min_salary = int(salary_match.group(1)) if salary_match else config.USER_MIN_SALARY

        return {
            "roles": self._infer_roles_from_goal(user_goal),
            "locations": self._infer_locations_from_goal(user_goal),
            "work_mode": work_mode,
            "min_salary": min_salary,
            "extra_keywords": [],
        }

    def build_profile_from_goal(self, user_goal: str) -> SearchProfile:
        self.log.info(f"Building search profile from goal: '{user_goal}'")

        prompt = f"""
User's job search goal:
"{user_goal}"

Extract the following parameters and return ONLY a JSON object with these keys:
- "roles": list of job roles/titles (e.g. ["AI Engineer", "ML Engineer"])
- "locations": list of cities (e.g. ["Bangalore", "Remote"])
- "work_mode": one of "remote", "onsite", "hybrid", or "any"
- "min_salary": integer in LPA (0 if not mentioned)
- "extra_keywords": list of extra keywords to add to the search (e.g. ["LLM", "deep learning"])

If something is not mentioned, use these defaults:
  roles = {config.USER_TARGET_ROLES}
  locations = {config.USER_TARGET_LOCATIONS}
  work_mode = "{config.USER_WORK_MODE}"
  min_salary = {config.USER_MIN_SALARY}
  extra_keywords = []
"""

        parsed = self.ask_llm_json(prompt, system=self.SYSTEM_PROMPT)
        if not parsed:
            strict_prompt = f"""
Return ONLY valid JSON. No prose, no markdown, no code block.

Schema:
{{
  "roles": ["..."],
  "locations": ["..."],
  "work_mode": "remote|onsite|hybrid|any",
  "min_salary": 0,
  "extra_keywords": []
}}

User goal: "{user_goal}"
"""
            parsed = self.ask_llm_json(
                strict_prompt,
                system=(
                    "You are a JSON API. Return exactly one JSON object matching schema."
                ),
                temperature=0.0,
                max_tokens=220,
            )

        if not parsed:
            self.log.warning("Falling back to local goal parsing because LLM response was not valid JSON.")
            parsed = self._fallback_profile_fields(user_goal)

        roles_raw = parsed.get("roles") or config.USER_TARGET_ROLES
        roles = [self._canonical_role(str(r)) for r in roles_raw if str(r).strip()]
        if not roles:
            roles = config.USER_TARGET_ROLES

        locations = parsed.get("locations") or config.USER_TARGET_LOCATIONS
        work_mode = self._normalise_work_mode(parsed.get("work_mode") or config.USER_WORK_MODE)

        min_salary = int(parsed.get("min_salary") or config.USER_MIN_SALARY)
        min_salary = self._normalise_min_salary_lpa(min_salary)
        if (not self._goal_mentions_salary(user_goal)) and min_salary > max(config.USER_MIN_SALARY, 30):
            # Prevent large hallucinated salary filters when user did not ask for salary.
            min_salary = config.USER_MIN_SALARY

        extra_keywords = [
            str(k).strip() for k in (parsed.get("extra_keywords") or []) if str(k).strip()
        ]

        self.profile = SearchProfile(
            goal=user_goal,
            roles=roles,
            locations=locations,
            work_mode=work_mode,
            min_salary=min_salary,
            min_confidence_score=config.MIN_CONFIDENCE_SCORE,
            max_applications=config.MAX_APPLICATIONS_PER_RUN,
            dry_run=config.DRY_RUN,
            extra_keywords=extra_keywords,
        )

        self.log.info(
            f"Search profile built:\n"
            f"  Roles       : {self.profile.roles}\n"
            f"  Locations   : {self.profile.locations}\n"
            f"  Work mode   : {self.profile.work_mode}\n"
            f"  Min salary  : {self.profile.min_salary} LPA\n"
            f"  Min score   : {self.profile.min_confidence_score}\n"
            f"  Max apps    : {self.profile.max_applications}\n"
            f"  Dry run     : {self.profile.dry_run}"
        )
        return self.profile

    def build_profile_from_config(self) -> SearchProfile:
        self.profile = SearchProfile(
            goal="Configured job search (from config.py & .env)",
            roles=config.USER_TARGET_ROLES,
            locations=config.USER_TARGET_LOCATIONS,
            work_mode=config.USER_WORK_MODE,
            min_salary=config.USER_MIN_SALARY,
            min_confidence_score=config.MIN_CONFIDENCE_SCORE,
            max_applications=config.MAX_APPLICATIONS_PER_RUN,
            dry_run=config.DRY_RUN,
        )
        self.log.info("Search profile loaded from config.")
        return self.profile

    def run(self, user_goal: str = "") -> SearchProfile:
        if user_goal.strip():
            return self.build_profile_from_goal(user_goal)
        return self.build_profile_from_config()


