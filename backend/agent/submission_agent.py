"""
submission_agent.py
-------------------
Browser automation for LinkedIn Easy Apply and best-effort external submissions.

The agent prefers to keep progressing through application flows by:
  - answering text, textarea, dropdown, combobox, radio, and checkbox questions
  - using resume/profile context plus LLM fallback when heuristics are weak
  - retrying after validation errors when possible
"""

import calendar
import re
import sys
import shutil
import tempfile
from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum
from pathlib import Path

from playwright.sync_api import BrowserContext, Locator, Page, sync_playwright

import config
from agent.base_agent import BaseAgent
from agent.errors import SubmissionError
from agent.planner_agent import JobListing
from agent.submission.flow_controller import attempt_action_with_repair
from agent.submission.form_fillers import extract_question_text, normalise_attrs
from agent.submission.result_detection import (
    collect_visible_errors,
    is_submission_confirmed,
)
from agent.submission.selectors import (
    APPLY_BUTTON_SELECTORS,
    EASY_APPLY_ACTION_SELECTORS,
    EXTERNAL_ACTION_SELECTORS,
)
from tools.cover_letter import CoverLetterAgent
from tools.resume_tools import extract_text_from_pdf


def _assert_playwright_start_supported() -> None:
    """Fail fast if this Windows environment cannot start Playwright subprocesses."""
    if sys.platform != "win32":
        return

    try:
        import _winapi
        from asyncio import windows_utils

        read_handle, write_handle = windows_utils.pipe(
            overlapped=(False, True),
            duplex=True,
        )
    except Exception as e:
        raise RuntimeError(
            "Playwright browser startup is blocked by Windows pipe permissions"
        ) from e
    else:
        _winapi.CloseHandle(read_handle)
        _winapi.CloseHandle(write_handle)


class SubmitResult(Enum):
    APPLIED = "Applied"
    DRY_RUN = "DryRun"
    FAILED = "Failed"
    SKIPPED = "Skipped"


@dataclass
class ApplicationResult:
    job: JobListing
    result: SubmitResult
    notes: str = ""


class SubmissionAgent(BaseAgent):
    """Strict LinkedIn Easy Apply automation."""

    def __init__(self, run_config=None):
        super().__init__("SubmissionAgent", run_config=run_config)
        self._playwright = None
        self._browser = None
        self._cover_letter_agent = None
        self._last_result_notes = ""
        self._answer_cache: dict[str, str] = {}
        self._resume_profile_cache: dict[str, str] | None = None
        self._temp_profile_dir: Path | None = None
        self.dry_run = (
            run_config.dry_run
            if run_config is not None
            else config.DRY_RUN
        )
        self.max_applications = (
            run_config.max_applications
            if run_config is not None
            else config.MAX_APPLICATIONS_PER_RUN
        )

    def start_browser(self) -> BrowserContext:
        """Launch a persistent Chromium context."""
        _assert_playwright_start_supported()
        self._playwright = sync_playwright().start()

        if config.USE_TEMP_BROWSER_PROFILE:
            self._temp_profile_dir = Path(tempfile.mkdtemp(prefix="job-agent-submit-"))
            user_data_dir = self._temp_profile_dir
            self.log.info(f"Using temporary browser profile: {user_data_dir}")
        else:
            user_data_dir = Path("chromium") / "user_data"
            user_data_dir.mkdir(parents=True, exist_ok=True)

        lock_file = user_data_dir / "SingletonLock"
        if lock_file.exists():
            lock_file.unlink()

        context = self._playwright.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir),
            headless=config.HEADLESS,
            ignore_https_errors=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--start-maximized",
            ],
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            no_viewport=True,
        )
        self.log.info(f"Browser started (headless={config.HEADLESS}).")
        self._browser = context
        return context

    def stop_browser(self) -> None:
        """Close the browser and Playwright."""
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()
        if self._temp_profile_dir:
            try:
                shutil.rmtree(self._temp_profile_dir, ignore_errors=True)
            except Exception:
                pass
            self._temp_profile_dir = None
        self.log.info("Browser stopped.")

    def _get_easy_apply_modal(self, page: Page) -> Locator | None:
        """Return the visible Easy Apply dialog if one is open."""
        selectors = [
            "div[role='dialog']",
            ".jobs-easy-apply-modal",
            ".artdeco-modal",
        ]
        for selector in selectors:
            try:
                modal = page.locator(selector).first
                if modal.count() > 0 and modal.is_visible():
                    return modal
            except Exception:
                continue
        return None

    def _get_external_form_scope(self, page: Page) -> Locator:
        """Return the most likely active external application form scope."""
        candidate_selectors = [
            "div[role='dialog'] form:visible",
            "form:visible",
            "main form:visible",
            "div[role='main'] form:visible",
        ]
        for selector in candidate_selectors:
            try:
                forms = page.locator(selector).all()
            except Exception:
                continue
            best_form = None
            best_score = -1
            for form in forms:
                try:
                    score = form.locator(
                        "input:visible, textarea:visible, select:visible, [role='combobox']:visible, input[type='radio']:visible, input[type='checkbox']:visible"
                    ).count()
                    if score > best_score and form.is_visible():
                        best_form = form
                        best_score = score
                except Exception:
                    continue
            if best_form is not None:
                return best_form
        return page.locator("body")

    def _close_easy_apply_modal(self, page: Page) -> None:
        """Dismiss the Easy Apply modal after a skip or dry run."""
        try:
            page.keyboard.press("Escape")
            self.human_pause(0.5)
        except Exception:
            pass

        discard_selectors = [
            "button:has-text('Discard')",
            "button:has-text('Dismiss')",
            "button[aria-label*='Discard']",
        ]
        for selector in discard_selectors:
            try:
                button = page.locator(selector).first
                if button.count() > 0 and button.is_visible():
                    button.click()
                    self.human_pause(0.5)
                    return
            except Exception:
                continue

    def _supported_text_input(self, attrs: str) -> bool:
        return any(
            key in attrs
            for key in [
                "phone",
                "mobile",
                "tel",
                "city",
                "location",
                "name",
                "first",
                "last",
                "linkedin",
                "profile",
                "website",
                "portfolio",
                "github",
                "year",
                "experience",
                "exp",
                "how many",
                "salary",
                "ctc",
                "compensation",
                "email",
            ]
        )

    def _should_ignore_field(self, attrs: str) -> bool:
        """Skip obvious page-level search/filter fields that are not application questions."""
        return any(
            token in attrs
            for token in [
                "search by keyword",
                "search by location",
                "search jobs",
                "filter",
                "sort by",
                "find jobs",
                "job search",
                "candidate search",
            ]
        )

    def _supported_textarea(self, attrs: str) -> bool:
        return any(
            key in attrs
            for key in ["cover", "letter", "message", "additional", "summary"]
        )

    def _normalise_attrs(self, locator: Locator) -> str:
        """Collect common identifying attributes for a form element."""
        return normalise_attrs(locator)

    def _extract_question_text(self, locator: Locator) -> str:
        """Infer the visible question text associated with a form control."""
        return extract_question_text(locator)

    def _build_application_context(self, resume_summary: str, cover_letter: str) -> str:
        """Build the candidate context passed to question-answering prompts."""
        context_parts = [
            f"Candidate name: {config.USER_NAME}",
            f"Email: {config.USER_EMAIL}",
            f"Phone: {config.USER_PHONE}",
            f"Location: {config.USER_LOCATION}",
            f"Years of experience: {config.USER_YEARS_EXPERIENCE}",
            f"Work authorized: {config.USER_WORK_AUTHORIZED}",
            f"Requires sponsorship: {config.USER_REQUIRES_SPONSORSHIP}",
        ]
        if config.USER_LINKEDIN_URL:
            context_parts.append(f"LinkedIn: {config.USER_LINKEDIN_URL}")
        if config.USER_PORTFOLIO_URL:
            context_parts.append(f"Portfolio: {config.USER_PORTFOLIO_URL}")
        if resume_summary:
            context_parts.append(f"Resume summary: {resume_summary[:1500]}")
        if cover_letter:
            context_parts.append(f"Cover letter draft: {cover_letter[:1200]}")
        return "\n".join(context_parts)

    def _extract_resume_profile(self, resume_summary: str, cover_letter: str) -> dict[str, str]:
        """
        Extract structured work-profile fields from resume context once per run.
        Falls back to conservative defaults when parsing fails.
        """
        if self._resume_profile_cache is not None:
            return self._resume_profile_cache

        current_year = date.today().year
        years_exp = self._safe_int(str(config.USER_YEARS_EXPERIENCE or "2"), fallback=2)
        start_year = max(2000, current_year - years_exp)
        profile = {
            "current_title": (config.USER_TARGET_ROLES[0] if config.USER_TARGET_ROLES else "Software Engineer"),
            "current_company": "",
            "city": config.USER_LOCATION,
            "start_month": "Jan",
            "start_year": str(start_year),
            "end_month": calendar.month_abbr[date.today().month],
            "end_year": str(current_year),
            "currently_work_here": "yes",
            "python_experience_years": str(years_exp),
            "summary": (resume_summary or "Experienced professional.").strip()[:500],
        }
        resume_text = extract_text_from_pdf(config.USER_RESUME_PATH)[:4000]
        profile.update(self._derive_resume_profile_from_text(resume_text, profile))

        prompt = f"""
Candidate context:
{self._build_application_context(resume_summary, cover_letter)}
Resume raw text (first 1800 chars):
{resume_text[:1800]}

Extract JSON only with:
{{
  "current_title": "short current/most recent job title",
  "current_company": "short company name (or empty)",
  "city": "city only",
  "start_month": "3-letter month like Jan",
  "start_year": "YYYY",
  "end_month": "3-letter month like Jan or empty if Present",
  "end_year": "YYYY or Present",
  "currently_work_here": "yes or no",
  "python_experience_years": "integer years for Python experience",
  "summary": "2 short lines about work/responsibilities"
}}
"""
        try:
            parsed = self.ask_llm_json(
                prompt,
                system=(
                    "Extract structured resume facts for job forms. "
                    "Return JSON only. Keep values short and factual."
                ),
                temperature=0.1,
                max_tokens=220,
            )
            if parsed:
                for key in profile:
                    value = str(parsed.get(key, "")).strip()
                    if value:
                        profile[key] = self._clean_profile_value(key, value)
        except Exception:
            pass

        # Final validation and normalization pass to prevent noisy/invalid values.
        profile = self._validate_resume_profile(profile)
        self._resume_profile_cache = profile
        return profile

    def _safe_int(self, value: str, fallback: int = 0) -> int:
        try:
            return int(re.findall(r"\d+", str(value))[0])
        except Exception:
            return fallback

    def _clean_short_field(self, text: str, max_len: int = 80) -> str:
        cleaned = re.sub(r"\s+", " ", (text or "").strip())
        cleaned = cleaned.split("\n")[0].strip()
        if cleaned.lower().startswith(("i am ", "my name is ", "experienced ")):
            return ""
        return cleaned[:max_len]

    def _clean_profile_value(self, key: str, value: str) -> str:
        if key in {"current_title", "current_company", "city"}:
            return self._clean_short_field(value, max_len=70)
        if key in {"start_month", "end_month"}:
            token = value.strip()[:3].title()
            return token if token in set(calendar.month_abbr[1:]) else ""
        if key in {"start_year", "end_year", "python_experience_years"}:
            return str(self._safe_int(value, fallback=0))
        if key == "currently_work_here":
            lowered = value.strip().lower()
            return "yes" if lowered in {"yes", "true", "1", "current", "present"} else "no"
        if key == "summary":
            return re.sub(r"\s+", " ", value).strip()[:500]
        return value

    def _derive_resume_profile_from_text(
        self,
        resume_text: str,
        base: dict[str, str],
    ) -> dict[str, str]:
        """Deterministically infer structured resume fields from raw resume text."""
        derived: dict[str, str] = {}
        text = resume_text or ""
        lower = text.lower()
        years = [int(y) for y in re.findall(r"\b(19\d{2}|20\d{2})\b", text)]
        years = [y for y in years if 1990 <= y <= date.today().year + 1]
        if years:
            start_year = min(years)
            end_year = max(years)
            derived["start_year"] = str(start_year)
            if any(tok in lower for tok in ["present", "current", "till date"]):
                derived["end_year"] = "Present"
                derived["currently_work_here"] = "yes"
            else:
                derived["end_year"] = str(end_year)
                derived["currently_work_here"] = "no"

        title_match = re.search(
            r"\b((?:ai|ml|machine learning|data|software|backend|full[- ]stack)\s+"
            r"(?:engineer|scientist|developer|researcher))\b",
            lower,
        )
        if title_match:
            derived["current_title"] = title_match.group(1).title()

        company_patterns = [
            r"\b(?:at|@)\s+([A-Z][A-Za-z0-9&\-. ]{2,40})",
            r"\bCompany[:\s]+([A-Z][A-Za-z0-9&\-. ]{2,40})",
        ]
        for pattern in company_patterns:
            match = re.search(pattern, text)
            if match:
                company = self._clean_short_field(match.group(1), max_len=60)
                if company and company.lower() not in {"linkedin", "github"}:
                    derived["current_company"] = company
                    break

        if "python" in lower:
            derived["python_experience_years"] = str(
                self._safe_int(base.get("python_experience_years", "2"), fallback=2)
            )
        return derived

    def _validate_resume_profile(self, profile: dict[str, str]) -> dict[str, str]:
        """Normalize and sanitize inferred profile to safe, form-friendly values."""
        now = date.today()
        start_year = self._safe_int(profile.get("start_year", ""), fallback=now.year - 2)
        end_year_raw = profile.get("end_year", "")
        end_year = None if end_year_raw.lower() == "present" else self._safe_int(end_year_raw, fallback=now.year)
        if start_year < 1990 or start_year > now.year:
            start_year = max(2000, now.year - 2)
        currently_work_here = profile.get("currently_work_here", "yes").lower() == "yes"

        if currently_work_here:
            profile["end_year"] = "Present"
        else:
            if end_year is None or end_year < start_year or end_year > now.year + 1:
                end_year = min(max(start_year, now.year), now.year + 1)
            profile["end_year"] = str(end_year)

        profile["start_year"] = str(start_year)
        profile["start_month"] = (
            profile.get("start_month", "Jan")[:3].title()
            if profile.get("start_month", "Jan")[:3].title() in set(calendar.month_abbr[1:])
            else "Jan"
        )
        end_month = profile.get("end_month", calendar.month_abbr[now.month])[:3].title()
        profile["end_month"] = end_month if end_month in set(calendar.month_abbr[1:]) else calendar.month_abbr[now.month]

        title = self._clean_short_field(profile.get("current_title", ""), max_len=60)
        company = self._clean_short_field(profile.get("current_company", ""), max_len=60)
        profile["current_title"] = title or (config.USER_TARGET_ROLES[0] if config.USER_TARGET_ROLES else "Software Engineer")
        profile["current_company"] = company
        profile["city"] = self._clean_short_field(profile.get("city", "") or config.USER_LOCATION, max_len=40) or config.USER_LOCATION

        py_years = self._safe_int(profile.get("python_experience_years", ""), fallback=self._safe_int(config.USER_YEARS_EXPERIENCE, fallback=2))
        profile["python_experience_years"] = str(max(0, min(py_years, 40)))
        profile["currently_work_here"] = "yes" if currently_work_here else "no"
        profile["summary"] = re.sub(r"\s+", " ", profile.get("summary", "")).strip()[:500]
        return profile

    def _choose_option_with_llm(
        self,
        question_text: str,
        options: list[str],
        resume_summary: str,
        cover_letter: str,
    ) -> str | None:
        """Choose the best option for a question using resume/profile context."""
        non_empty = [opt.strip() for opt in options if opt and opt.strip()]
        if not non_empty:
            return None

        cache_key = f"option::{question_text.lower()}::{'||'.join(non_empty).lower()}"
        if cache_key in self._answer_cache:
            cached = self._answer_cache[cache_key]
            return cached if cached in non_empty else None

        prompt = f"""
Candidate context:
{self._build_application_context(resume_summary, cover_letter)}

Application question:
{question_text or "Choose the best matching option."}

Available options:
{chr(10).join(f"- {option}" for option in non_empty)}

Return ONLY the exact option text that should be selected.
"""
        try:
            raw = self.ask_llm(
                prompt,
                system=(
                    "You are helping complete a job application form. "
                    "Choose the single best option using the candidate's resume/profile. "
                    "Return only one option exactly as written."
                ),
                temperature=0.1,
                max_tokens=120,
            ).strip()
            cleaned = raw.strip().strip('"').strip("'")
            for option in non_empty:
                if cleaned.lower() == option.lower():
                    self._answer_cache[cache_key] = option
                    return option
            for option in non_empty:
                if cleaned.lower() in option.lower() or option.lower() in cleaned.lower():
                    self._answer_cache[cache_key] = option
                    return option
        except Exception as e:
            self.log.debug(f"LLM option choice failed for '{question_text}': {e}")
        return None

    def _answer_free_text_with_llm(
        self,
        question_text: str,
        resume_summary: str,
        cover_letter: str,
        max_chars: int = 400,
    ) -> str:
        """Generate a concise text answer for an arbitrary application question."""
        cache_key = f"text::{question_text.lower()}::{max_chars}"
        if cache_key in self._answer_cache:
            return self._answer_cache[cache_key]

        prompt = f"""
Candidate context:
{self._build_application_context(resume_summary, cover_letter)}

Application question:
{question_text or "Provide an appropriate concise answer for the application field."}

Write a concise professional answer grounded in the candidate context.
Keep it under {max_chars} characters.
Return only the answer text.
"""
        try:
            raw = self.ask_llm(
                prompt,
                system=(
                    "You are completing a job application on behalf of a candidate. "
                    "Answer truthfully using only the supplied resume/profile context. "
                    "Be concise and professional. Return only the answer text."
                ),
                temperature=0.2,
                max_tokens=200,
            ).strip()
            answer = re.sub(r"\s+", " ", raw).strip().strip('"').strip("'")
            if answer:
                answer = answer[:max_chars].strip()
                self._answer_cache[cache_key] = answer
                return answer
        except Exception as e:
            self.log.debug(f"LLM text answer failed for '{question_text}': {e}")
        return ""

    def _infer_text_answer(self, attrs: str, resume_summary: str, cover_letter: str) -> str:
        """Best-effort answer generation for visible text inputs."""
        profile = self._extract_resume_profile(resume_summary, cover_letter)
        attrs_lower = attrs.lower()

        if any(k in attrs_lower for k in ["your title", "job title", "title", "position", "designation"]):
            return profile.get("current_title", "") or (config.USER_TARGET_ROLES[0] if config.USER_TARGET_ROLES else "Software Engineer")
        if any(k in attrs_lower for k in ["company", "employer", "organization", "organisation"]):
            return profile.get("current_company", "") or "Confidential"
        if any(k in attrs for k in ["phone", "mobile", "tel"]):
            return config.USER_PHONE
        if any(k in attrs for k in ["email", "mail"]):
            return config.USER_EMAIL
        if "last" in attrs:
            parts = config.USER_NAME.split()
            return parts[-1] if len(parts) > 1 else config.USER_NAME
        if "full name" in attrs:
            return config.USER_NAME
        if any(k in attrs for k in ["first", "given"]):
            return config.USER_NAME.split()[0] if config.USER_NAME else ""
        if "name" in attrs:
            return config.USER_NAME
        if any(k in attrs for k in ["city", "location", "address"]):
            return profile.get("city", "") or config.USER_LOCATION
        if any(k in attrs for k in ["linkedin", "profile"]):
            return config.USER_LINKEDIN_URL
        if any(k in attrs for k in ["website", "portfolio", "github"]):
            return config.USER_PORTFOLIO_URL
        if any(k in attrs for k in ["year", "experience", "exp", "how many"]):
            if "python" in attrs_lower:
                return profile.get("python_experience_years", str(config.USER_YEARS_EXPERIENCE))
            return str(config.USER_YEARS_EXPERIENCE)
        if any(k in attrs_lower for k in ["from year", "start year", "year from"]):
            return profile.get("start_year", str(date.today().year - 2))
        if any(k in attrs_lower for k in ["to year", "end year", "year to"]):
            return str(date.today().year) if profile.get("end_year", "").lower() == "present" else profile.get("end_year", str(date.today().year))
        if any(k in attrs_lower for k in ["from month", "start month", "month from"]):
            return profile.get("start_month", "Jan")
        if any(k in attrs_lower for k in ["to month", "end month", "month to"]):
            return profile.get("end_month", calendar.month_abbr[date.today().month])
        if any(k in attrs_lower for k in ["description", "responsibilities", "summary of role", "work summary"]):
            return profile.get("summary", "") or (resume_summary or "").strip()[:350]
        if any(k in attrs_lower for k in ["salary", "ctc", "compensation"]):
            lpa = max(int(config.USER_MIN_SALARY or 0), 6)
            annual_inr = lpa * 100000
            return str(max(annual_inr, 1000))
        if any(k in attrs_lower for k in ["notice", "joining", "available", "availability"]):
            if any(k in attrs_lower for k in ["day", "days", "in days"]):
                return "30"
            return "Immediate"
        if any(k in attrs for k in ["start date", "available from", "joining date"]):
            return (date.today() + timedelta(days=7)).isoformat()
        if any(k in attrs for k in ["dob", "date of birth", "birth date"]):
            return "1999-01-01"
        if any(k in attrs for k in ["visa", "sponsor", "authorized", "authorised", "eligible"]):
            return "Yes" if config.USER_WORK_AUTHORIZED.lower() == "yes" else "No"
        if any(k in attrs for k in ["why", "motivation", "interest", "fit", "about you"]):
            return (resume_summary or cover_letter or "Experienced software professional.").strip()[:300]
        if any(k in attrs for k in ["university", "college", "degree", "education"]):
            return "Bachelor's"
        if any(k in attrs for k in ["current company", "employer"]):
            return "Open to opportunities"
        answer = self._answer_free_text_with_llm(attrs, resume_summary, cover_letter, max_chars=200)
        if answer:
            return answer
        return (resume_summary or cover_letter or config.USER_NAME or "N/A").strip()[:200]

    def _infer_textarea_answer(self, attrs: str, resume_summary: str, cover_letter: str) -> str:
        """Best-effort answer generation for textareas."""
        if self._supported_textarea(attrs):
            return cover_letter or resume_summary or "I am excited to contribute to this role."
        answer = self._answer_free_text_with_llm(attrs, resume_summary, cover_letter, max_chars=1200)
        if answer:
            return answer
        return resume_summary or cover_letter or "I am interested in this opportunity."

    def _is_placeholder_option(self, text: str) -> bool:
        cleaned = re.sub(r"\s+", " ", (text or "").strip().lower())
        if not cleaned:
            return True
        placeholder_tokens = {
            "-",
            "--",
            "select",
            "select option",
            "select an option",
            "choose",
            "choose option",
            "choose an option",
            "please select",
            "please choose",
            "none",
            "n/a",
            "month",
            "year",
        }
        return cleaned in placeholder_tokens or cleaned.startswith("select ")

    def _normalise_option_list(self, options: list[str]) -> list[str]:
        """Drop placeholder/empty options and de-duplicate while preserving order."""
        cleaned: list[str] = []
        seen: set[str] = set()
        for option in options:
            text = re.sub(r"\s+", " ", (option or "").strip())
            if not text or self._is_placeholder_option(text):
                continue
            key = text.lower()
            if key in seen:
                continue
            seen.add(key)
            cleaned.append(text)
        return cleaned

    def _infer_option_choice(self, attrs: str, options: list[str]) -> str | None:
        """Pick a reasonable option from a dropdown/radio style question."""
        non_empty = self._normalise_option_list(options)
        if not non_empty:
            return None

        lowered_options = [(o, o.lower()) for o in non_empty]
        attrs_lower = attrs.lower()

        def pick_contains(*tokens: str) -> str | None:
            for original, lowered in lowered_options:
                if any(token in lowered for token in tokens):
                    return original
            return None

        yes_opt = pick_contains("yes", "true", "i do", "affirmative")
        no_opt = pick_contains("no", "false", "i don't", "do not")
        if yes_opt and no_opt:
            years_exp = self._safe_int(str(config.USER_YEARS_EXPERIENCE or "2"), fallback=2)
            if "senior" in attrs_lower or "lead" in attrs_lower:
                return yes_opt if years_exp >= 4 else no_opt
            if "startup" in attrs_lower:
                return yes_opt if years_exp >= 2 else no_opt
            if "python" in attrs_lower:
                return yes_opt if years_exp >= 1 else no_opt
            if any(k in attrs_lower for k in ["start immediately", "immediately", "urgent", "join immediately", "notice period"]):
                return yes_opt
            if any(k in attrs_lower for k in ["authorized", "authoriz", "eligible", "legally"]):
                return yes_opt if config.USER_WORK_AUTHORIZED.lower() == "yes" else no_opt
            if "sponsor" in attrs_lower or "visa" in attrs_lower:
                return yes_opt if config.USER_REQUIRES_SPONSORSHIP.lower() == "yes" else no_opt

        # Resume-aware timeline choices for month/year dropdowns in work-history forms.
        now = date.today()
        try:
            years_exp = int(str(config.USER_YEARS_EXPERIENCE or "2"))
        except Exception:
            years_exp = 2
        start_year = max(2000, now.year - years_exp)

        month_names = [calendar.month_name[i].lower() for i in range(1, 13)] + [calendar.month_abbr[i].lower() for i in range(1, 13)]
        if any(any(m in opt for m in month_names) for _, opt in lowered_options):
            if any(k in attrs_lower for k in ["from", "start"]):
                return pick_contains("jan") or non_empty[0]
            if any(k in attrs_lower for k in ["to", "end"]):
                return pick_contains(calendar.month_name[now.month].lower(), calendar.month_abbr[now.month].lower()) or non_empty[0]

        numeric_year_options = []
        for original, lowered in lowered_options:
            m = re.search(r"\b(19\d{2}|20\d{2}|21\d{2})\b", lowered)
            if m:
                numeric_year_options.append((original, int(m.group(1))))
        if numeric_year_options:
            if any(k in attrs_lower for k in ["from", "start"]):
                target = min(numeric_year_options, key=lambda item: abs(item[1] - start_year))[0]
                return target
            if any(k in attrs_lower for k in ["to", "end"]):
                return pick_contains("present", "current") or min(
                    numeric_year_options,
                    key=lambda item: abs(item[1] - now.year),
                )[0]

        if any(k in attrs for k in ["country", "code"]):
            return pick_contains("india", "+91") or non_empty[0]
        if any(k in attrs for k in ["experience", "year"]):
            years = str(config.USER_YEARS_EXPERIENCE)
            return pick_contains(years) or non_empty[0]
        if any(k in attrs for k in ["education", "degree", "university", "college"]):
            return pick_contains("bachelor", "b.tech", "b.e") or non_empty[0]
        if any(k in attrs for k in ["authorized", "authoriz", "eligible", "legally"]):
            return pick_contains("yes") if config.USER_WORK_AUTHORIZED.lower() == "yes" else pick_contains("no")
        if "sponsor" in attrs or "visa" in attrs:
            need = config.USER_REQUIRES_SPONSORSHIP.lower() == "yes"
            return pick_contains("yes") if need else pick_contains("no")
        if any(k in attrs for k in ["relocate", "remote", "hybrid", "onsite"]):
            return pick_contains("yes", "hybrid", "remote", "onsite") or non_empty[0]
        if any(k in attrs for k in ["have", "do you", "background", "check"]):
            return pick_contains("yes") or non_empty[0]
        return non_empty[0]

    def _resolve_option_choice(
        self,
        question_text: str,
        attrs: str,
        options: list[str],
        resume_summary: str,
        cover_letter: str,
    ) -> str | None:
        """Choose an option using heuristics first, then LLM fallback."""
        cleaned_options = self._normalise_option_list(options)
        if not cleaned_options:
            return None

        merged_question = f"{question_text} {attrs}".strip()
        target = self._infer_option_choice(merged_question, cleaned_options)
        if target:
            return target
        return self._choose_option_with_llm(
            question_text or attrs,
            cleaned_options,
            resume_summary,
            cover_letter,
        )

    def _form_needs_cover_letter(self, page: Locator) -> bool:
        """Return True when the current form exposes a supported cover-letter field."""
        for ta in page.locator("textarea:visible").all():
            try:
                attrs = " ".join([
                    (ta.get_attribute("id") or ""),
                    (ta.get_attribute("name") or ""),
                    (ta.get_attribute("placeholder") or ""),
                    (ta.get_attribute("aria-label") or ""),
                ]).lower()
                if self._supported_textarea(attrs):
                    return True
            except Exception:
                continue
        return False

    def _generate_cover_letter_if_needed(
        self,
        page: Locator,
        job: JobListing,
        cover_letter: str,
        resume_summary: str,
    ) -> str:
        """Generate a fresh cover letter only when the form actually needs one."""
        if cover_letter.strip() or not self._form_needs_cover_letter(page):
            return cover_letter

        if self._cover_letter_agent is None:
            self._cover_letter_agent = CoverLetterAgent()

        self.log.info(f"Generating fresh cover letter on demand for {job.company}")
        return self._cover_letter_agent.generate(job, resume_summary)

    def _get_primary_action(self, modal: Locator) -> tuple[str, Locator | None]:
        """Return the current modal action button and its type."""
        for action_type, selector in EASY_APPLY_ACTION_SELECTORS:
            try:
                button = modal.locator(selector).first
                if button.count() > 0 and button.is_visible():
                    return action_type, button
            except Exception:
                continue
        return "none", None

    def _get_external_primary_action(self, page: Page) -> tuple[str, Locator | None]:
        """Return the current visible action button on an external apply page."""
        for action_type, selector in EXTERNAL_ACTION_SELECTORS:
            try:
                button = page.locator(selector).first
                if button.count() > 0 and button.is_visible():
                    return action_type, button
            except Exception:
                continue
        return "none", None

    def _get_apply_button(self, page: Page) -> tuple[str, Locator | None]:
        """Return the best available apply button on the LinkedIn job page."""
        for selector in APPLY_BUTTON_SELECTORS["easy"]:
            try:
                button = page.locator(selector).first
                if button.count() > 0 and button.is_visible():
                    return "easy", button
            except Exception:
                continue

        for selector in APPLY_BUTTON_SELECTORS["external"]:
            try:
                button = page.locator(selector).first
                if button.count() == 0 or not button.is_visible():
                    continue
                text = (button.inner_text() or "").strip().lower()
                if "easy apply" in text:
                    continue
                return "external", button
            except Exception:
                continue
        return "none", None

    def _is_submission_confirmed(self, page: Page) -> bool:
        """Detect common post-submit confirmation text on LinkedIn or external pages."""
        return is_submission_confirmed(page)

    def _looks_like_success_after_submit(self, page: Page) -> bool:
        """Fallback success detection when LinkedIn closes the modal without obvious text."""
        if self._is_submission_confirmed(page):
            return True

        try:
            modal = self._get_easy_apply_modal(page)
            if modal is None and self._is_already_applied(page):
                return True
        except Exception:
            pass

        try:
            if self._is_already_applied(page):
                return True
        except Exception:
            pass

        return False

    def _collect_visible_errors(self, page: Locator | Page) -> list[str]:
        """Collect visible validation and inline error messages from the current form."""
        return collect_visible_errors(page)

    def _save_debug_snapshot(self, page: Page, job: JobListing, stage: str) -> str:
        """Save a screenshot to help troubleshoot failed application steps."""
        debug_dir = Path("data") / "debug"
        debug_dir.mkdir(parents=True, exist_ok=True)
        safe_stage = re.sub(r"[^a-z0-9_-]+", "_", stage.lower())
        path = debug_dir / f"{job.job_id}_{safe_stage}.png"
        try:
            page.screenshot(path=str(path), full_page=True)
            return str(path)
        except Exception:
            return ""

    def _repair_invalid_fields(
        self,
        page: Locator,
        resume_summary: str,
        cover_letter: str,
    ) -> None:
        """Retry filling fields that LinkedIn marked invalid."""
        try:
            if page.locator("input[aria-invalid='true']:visible").count() > 0:
                self._fill_text_inputs(page, resume_summary, cover_letter)
            if page.locator("textarea[aria-invalid='true']:visible").count() > 0:
                self._fill_textareas(page, cover_letter, resume_summary)
            if page.locator("select[aria-invalid='true']:visible").count() > 0:
                self._fill_dropdowns(page, resume_summary, cover_letter)
            if page.locator("[role='combobox'][aria-invalid='true']:visible").count() > 0:
                self._fill_comboboxes(page, resume_summary, cover_letter)
        except Exception:
            # If invalid targeting fails, still do a best-effort refill pass.
            self._fill_text_inputs(page, resume_summary, cover_letter)
            self._fill_textareas(page, cover_letter, resume_summary)
            self._fill_dropdowns(page, resume_summary, cover_letter)
            self._fill_comboboxes(page, resume_summary, cover_letter)
        self._fill_radios(page, resume_summary, cover_letter)
        self._force_answer_required_radios(page, resume_summary, cover_letter)
        self._fill_checkboxes(page, resume_summary, cover_letter)
        self._force_fill_remaining_select_like(page, resume_summary, cover_letter)

    def _force_fill_remaining_select_like(
        self,
        page: Locator,
        resume_summary: str,
        cover_letter: str,
    ) -> None:
        """
        Last-resort repair for unanswered select-like controls after validation errors.
        Prefer any concrete option over leaving placeholder values.
        """
        for sel in page.locator("select:visible").all():
            try:
                current = (sel.input_value() or "").strip().lower()
                if current and current not in {"", "select", "select an option", "choose", "choose an option"}:
                    continue
                options = [o.strip() for o in sel.locator("option").all_text_contents() if o.strip()]
                options = [
                    o for o in options
                    if o.lower() not in {"select", "select an option", "choose", "choose an option", "-", "--"}
                ]
                if not options:
                    continue
                question_text = self._extract_question_text(sel)
                attrs = self._normalise_attrs(sel)
                target = self._resolve_option_choice(
                    question_text,
                    attrs,
                    options,
                    resume_summary,
                    cover_letter,
                ) or options[0]
                try:
                    sel.select_option(label=target)
                except Exception:
                    sel.select_option(index=1 if len(options) > 1 else 0)
                self.human_pause(0.2)
            except Exception:
                continue

        for combo in page.locator("[role='combobox']:visible, button[aria-haspopup='listbox']:visible").all():
            try:
                current_value = (
                    combo.get_attribute("value")
                    or combo.get_attribute("aria-label")
                    or (combo.text_content() or "")
                ).strip().lower()
                if current_value and current_value not in {"select", "select an option", "choose", "choose an option"}:
                    continue

                combo.click()
                self.human_pause(0.4)
                nodes = page.page.locator("[role='option']:visible, li[role='option']:visible").all()
                option_texts = [
                    (node.text_content() or "").strip()
                    for node in nodes
                    if (node.text_content() or "").strip()
                ]
                option_texts = [
                    t for t in option_texts
                    if t.lower() not in {"select", "select an option", "choose", "choose an option", "-", "--"}
                ]
                if not nodes or not option_texts:
                    try:
                        page.page.keyboard.press("Escape")
                    except Exception:
                        pass
                    continue

                question_text = self._extract_question_text(combo)
                attrs = self._normalise_attrs(combo)
                target = self._resolve_option_choice(
                    question_text,
                    attrs,
                    option_texts,
                    resume_summary,
                    cover_letter,
                ) or option_texts[0]

                clicked = False
                for node in nodes:
                    text = (node.text_content() or "").strip()
                    if text and text.lower() == target.lower():
                        node.click()
                        clicked = True
                        break
                if not clicked:
                    nodes[0].click()
                self.human_pause(0.2)
            except Exception:
                try:
                    page.page.keyboard.press("Escape")
                except Exception:
                    pass
                continue

    def _attempt_action_with_repair(
        self,
        action_button: Locator,
        action_type: str,
        page: Page,
        form_scope: Locator,
        job: JobListing,
        resume_summary: str,
        cover_letter: str,
    ) -> tuple[bool, list[str]]:
        """Click an action, then retry once if visible validation errors appear."""
        return attempt_action_with_repair(
            agent=self,
            action_button=action_button,
            action_type=action_type,
            page=page,
            form_scope=form_scope,
            job=job,
            resume_summary=resume_summary,
            cover_letter=cover_letter,
        )

    def _wait_for_submission_outcome(self, page: Page, job: JobListing) -> SubmitResult:
        """Wait briefly for a post-submit outcome before classifying the attempt."""
        poll_delays = [2.0, 3.0, 4.0]
        for delay in poll_delays:
            self.human_pause(delay / max(config.HUMAN_DELAY_MS / 1000, 0.1))
            if self._looks_like_success_after_submit(page):
                self._last_result_notes = "Detected post-submit applied state."
                self.log.info(f"Applied to: {job.title} @ {job.company}")
                return SubmitResult.APPLIED

        try:
            page.reload(wait_until="domcontentloaded", timeout=20_000)
            self.human_pause(1.5)
            if self._looks_like_success_after_submit(page):
                self._last_result_notes = "Detected applied state after refresh."
                self.log.info(f"Applied to: {job.title} @ {job.company}")
                return SubmitResult.APPLIED
        except Exception as e:
            self.log.debug(f"Post-submit refresh check failed for {job.title}: {e}")

        errors = self._collect_visible_errors(page)
        debug_path = self._save_debug_snapshot(page, job, "submit_failed")
        note_parts = ["Submit clicked but no confirmation or applied-state badge detected."]
        if errors:
            note_parts.append(f"Visible errors: {' | '.join(errors[:3])}")
        if debug_path:
            note_parts.append(f"Screenshot: {debug_path}")
        self._last_result_notes = " ".join(note_parts)
        self.log.warning(f"Submit clicked but no confirmation for: {job.title}")
        return SubmitResult.FAILED

    def _apply_external_flow(
        self,
        page: Page,
        job: JobListing,
        cover_letter: str,
        resume_summary: str,
    ) -> SubmitResult:
        """Best-effort external apply flow for non-Easy-Apply buttons."""
        self.log.info(f"Attempting external apply flow for: {job.title}")
        max_steps = 12
        for step in range(1, max_steps + 1):
            self.log.info(f"Processing external apply step {step} for: {job.title}")
            form_scope = self._get_external_form_scope(page)
            self._upload_resume(form_scope)
            self._fill_text_inputs(form_scope, resume_summary, cover_letter)
            self._fill_textareas(form_scope, cover_letter, resume_summary)
            self._fill_dropdowns(form_scope, resume_summary, cover_letter)
            self._fill_comboboxes(form_scope, resume_summary, cover_letter)
            self._fill_radios(form_scope, resume_summary, cover_letter)
            self._fill_checkboxes(form_scope, resume_summary, cover_letter)

            action_type, action_button = self._get_external_primary_action(page)
            if action_button is None:
                if self._is_submission_confirmed(page):
                    self.log.info(f"Applied to: {job.title} @ {job.company}")
                    return SubmitResult.APPLIED
                debug_path = self._save_debug_snapshot(page, job, f"external_step_{step}_no_action")
                note_parts = ["No external apply action button was available."]
                if debug_path:
                    note_parts.append(f"Screenshot: {debug_path}")
                self._last_result_notes = " ".join(note_parts)
                self.log.warning(f"External apply stalled with no action button for: {job.title}")
                return SubmitResult.FAILED

            if action_type == "submit":
                if self.dry_run:
                    self.log.info(f"DRY RUN - external apply is ready for submit on step {step}: {job.title}")
                    return SubmitResult.DRY_RUN

                success, errors = self._attempt_action_with_repair(
                    action_button,
                    action_type,
                    page,
                    form_scope,
                    job,
                    resume_summary,
                    cover_letter,
                )
                if not success:
                    self._last_result_notes = f"External form validation errors: {' | '.join(errors[:3])}"
                    return SubmitResult.FAILED
                self.human_pause(5.0)
                if self._looks_like_success_after_submit(page):
                    self._last_result_notes = "Detected external apply confirmation."
                    self.log.info(f"Applied to: {job.title} @ {job.company}")
                    return SubmitResult.APPLIED

                self._last_result_notes = "External submit clicked but no confirmation detected."
                self.log.warning(f"External submit clicked but no confirmation for: {job.title}")
                return SubmitResult.FAILED

            success, errors = self._attempt_action_with_repair(
                action_button,
                action_type,
                page,
                form_scope,
                job,
                resume_summary,
                cover_letter,
            )
            if not success:
                self._last_result_notes = f"External step validation errors: {' | '.join(errors[:3])}"
                return SubmitResult.FAILED
            self.log.info(f"Advanced external apply via {action_type} on step {step}")
            self.human_pause(1.5)

        debug_path = self._save_debug_snapshot(page, job, "external_step_limit")
        note_parts = [f"External apply flow exceeded {max_steps} steps."]
        if debug_path:
            note_parts.append(f"Screenshot: {debug_path}")
        self._last_result_notes = " ".join(note_parts)
        self.log.warning(f"External apply exceeded {max_steps} steps for: {job.title}")
        return SubmitResult.FAILED

    def _supported_select(self, attrs: str) -> bool:
        return any(
            key in attrs
            for key in [
                "multiplechoice",
                "country",
                "code",
                "experience",
                "year",
                "education",
                "degree",
                "authorized",
                "authoriz",
                "eligible",
                "sponsor",
                "have",
                "do you",
                "worked as",
                "have worked",
                "experience with",
                "years of work",
                "proficient",
                "familiar",
                "comfortable",
            ]
        )

    def _supported_radio_group(self, legend: str) -> bool:
        return any(
            key in legend
            for key in [
                "authorized",
                "eligible",
                "legally",
                "sponsor",
                "visa",
                "bachelor",
                "degree",
                "education",
                "master",
                "background check",
                "background",
                "start immediately",
                "immediately",
                "urgent",
                "notice period",
                "join immediately",
                "relocate",
                "willing",
            ]
        )

    def _upload_resume(self, page: Locator) -> None:
        """Upload the resume file if the current form step exposes a file input."""
        if not config.USER_RESUME_PATH.exists():
            return
        try:
            file_input = page.locator("input[type='file']").first
            if file_input.count() > 0:
                file_input.set_input_files(str(config.USER_RESUME_PATH))
                self.log.info("Uploaded resume to Easy Apply form")
                self.human_pause(1.0)
        except Exception as e:
            self.log.debug(f"Resume upload skipped on this step: {e}")

    def _fill_text_inputs(self, page: Locator, resume_summary: str, cover_letter: str) -> None:
        """Fill visible text-like inputs with best-effort answers."""
        inputs = page.locator(
            "input[type='text']:visible, "
            "input[type='search']:visible, "
            "input[type='number']:visible, "
            "input[type='tel']:visible, "
            "input[type='email']:visible, "
            "input[type='url']:visible, "
            "input[type='date']:visible"
        ).all()
        for inp in inputs:
            try:
                if inp.input_value():
                    continue
                attrs = self._normalise_attrs(inp)
                question_text = self._extract_question_text(inp)
                if self._should_ignore_field(f"{question_text} {attrs}".strip().lower()):
                    continue
                answer = self._infer_text_answer(
                    f"{question_text} {attrs}".strip(),
                    resume_summary,
                    cover_letter,
                )
                if not answer:
                    continue
                inp.click()
                try:
                    inp.press("Control+A")
                except Exception:
                    pass
                inp.fill(answer)
                if any(k in attrs for k in ["location", "city", "geo-location", "typeahead"]):
                    self.human_pause(0.8)
                    try:
                        suggestion = page.locator(
                            ".basic-typeahead__selectable:visible, "
                            ".artdeco-typeahead__result:visible, "
                            "[role='option']:visible"
                        ).first
                        if suggestion.count() > 0:
                            suggestion.click()
                            self.human_pause(0.4)
                    except Exception:
                        pass
                    try:
                        inp.press("ArrowDown")
                        self.human_pause(0.2)
                    except Exception:
                        pass
                    try:
                        inp.press("Enter")
                        self.human_pause(0.4)
                    except Exception:
                        pass
                self.log.info(f"Filled text input: {question_text or attrs or 'unnamed field'}")
                self.human_pause(0.3)
            except Exception:
                pass

    def _fill_textareas(self, page: Locator, cover_letter: str, resume_summary: str) -> None:
        """Fill visible textareas with best-effort answers."""
        for ta in page.locator("textarea:visible").all():
            try:
                if ta.input_value():
                    continue
                attrs = self._normalise_attrs(ta)
                question_text = self._extract_question_text(ta)
                if self._should_ignore_field(f"{question_text} {attrs}".strip().lower()):
                    continue
                answer = self._infer_textarea_answer(
                    f"{question_text} {attrs}".strip(),
                    resume_summary,
                    cover_letter,
                )
                if not answer:
                    continue
                ta.fill(answer)
                self.log.info(f"Filled textarea: {question_text or attrs or 'unnamed field'}")
                self.human_pause(0.3)
            except Exception:
                pass

    def _fill_dropdowns(self, page: Locator, resume_summary: str, cover_letter: str) -> None:
        """Fill supported dropdowns only."""
        for sel in page.locator("select:visible").all():
            try:
                current_value = (sel.input_value() or "").strip()
                if current_value and not self._is_placeholder_option(current_value):
                    continue
                attrs = self._normalise_attrs(sel)
                question_text = self._extract_question_text(sel)
                merged_prompt = f"{question_text} {attrs}".strip().lower()
                if self._should_ignore_field(merged_prompt):
                    continue
                options = self._normalise_option_list(sel.locator("option").all_text_contents())
                target = self._resolve_option_choice(
                    question_text,
                    attrs,
                    options,
                    resume_summary,
                    cover_letter,
                )
                if not target:
                    continue

                try:
                    sel.select_option(label=target)
                except Exception:
                    try:
                        sel.select_option(value=target)
                    except Exception:
                        sel.select_option(index=1 if len(options) > 1 else 0)

                # Verify we did not remain on placeholder after selection.
                selected_text = ""
                try:
                    selected_text = (sel.locator("option:checked").first.inner_text() or "").strip()
                except Exception:
                    pass
                if self._is_placeholder_option(selected_text) and len(options) > 0:
                    try:
                        sel.select_option(label=options[0])
                        target = options[0]
                    except Exception:
                        pass
                self.log.info(f"Selected dropdown answer: {question_text or attrs or 'unnamed field'} -> {target}")
                self.human_pause(0.3)
            except Exception:
                pass

    def _fill_comboboxes(self, page: Locator, resume_summary: str, cover_letter: str) -> None:
        """Fill visible custom combobox/listbox widgets with best-effort answers."""
        combo_selectors = [
            "[role='combobox']:visible",
            "button[aria-haspopup='listbox']:visible",
            "button[aria-expanded='false']:visible",
        ]
        seen_keys: set[str] = set()

        for selector in combo_selectors:
            for combo in page.locator(selector).all():
                try:
                    attrs = self._normalise_attrs(combo)
                    if not attrs:
                        attrs = (combo.text_content() or "").strip().lower()
                    if not attrs:
                        continue

                    key = f"{selector}:{attrs}"
                    if key in seen_keys:
                        continue
                    seen_keys.add(key)

                    current_value = (
                        combo.get_attribute("value")
                        or combo.get_attribute("aria-label")
                        or (combo.text_content() or "")
                    ).strip().lower()
                    if current_value and not self._is_placeholder_option(current_value):
                        continue

                    combo.click()
                    self.human_pause(0.5)

                    option_locators = [
                        page.locator("[role='option']:visible"),
                        page.locator("li[role='option']:visible"),
                        page.locator(".artdeco-typeahead__result:visible"),
                        page.locator(".fb-dash-form-element__dropdown-option:visible"),
                    ]

                    option_nodes = []
                    option_texts: list[str] = []
                    for option_locator in option_locators:
                        nodes = option_locator.all()
                        texts = [
                            (node.text_content() or "").strip()
                            for node in nodes
                            if (node.text_content() or "").strip()
                        ]
                        if texts:
                            option_nodes = nodes
                            option_texts = texts
                            break

                    # Keep only concrete options and keep node mapping aligned.
                    filtered_pairs = [
                        (node, re.sub(r"\s+", " ", text).strip())
                        for node, text in zip(option_nodes, option_texts)
                        if not self._is_placeholder_option(text)
                    ]
                    option_nodes = [node for node, _ in filtered_pairs]
                    option_texts = [text for _, text in filtered_pairs]

                    target = self._resolve_option_choice(
                        self._extract_question_text(combo),
                        attrs,
                        option_texts,
                        resume_summary,
                        cover_letter,
                    )
                    if not target or not option_nodes:
                        page.page.keyboard.press("Escape")
                        self.human_pause(0.2)
                        continue

                    selected = False
                    for node in option_nodes:
                        text = re.sub(r"\s+", " ", (node.text_content() or "").strip())
                        if (
                            text.lower() == target.lower()
                            or target.lower() in text.lower()
                            or text.lower() in target.lower()
                        ):
                            node.click()
                            selected = True
                            break

                    if not selected and option_nodes:
                        option_nodes[0].click()
                        if option_texts:
                            target = option_texts[0]

                    self.log.info(f"Selected combobox option: {attrs or 'unnamed field'} -> {target}")
                    self.human_pause(0.4)
                except Exception:
                    try:
                        page.page.keyboard.press("Escape")
                    except Exception:
                        pass
                    continue

    def _fill_radios(self, page: Locator, resume_summary: str, cover_letter: str) -> None:
        """Fill visible radio groups with best-effort answers."""

        def _answer_group(question_text: str, radios: list) -> None:
            if not radios or any(r.is_checked() for r in radios):
                return

            option_texts: list[str] = []
            radio_details = []
            for radio in radios:
                radio_id = radio.get_attribute("id")
                label_text = ""
                if radio_id:
                    label = page.locator(f"label[for='{radio_id}']")
                    if label.count() > 0:
                        label_text = (label.first.text_content() or "").strip()
                value = (radio.get_attribute("value") or "").strip()
                option_label = label_text or value
                option_texts.append(option_label)
                radio_details.append((radio, option_label.lower(), value.lower()))

            # Handle common yes/no groups even when question text is weak.
            lowered_opts = [o.lower() for o in option_texts]
            yes_no_group = ("yes" in lowered_opts and "no" in lowered_opts)

            if not yes_no_group and not self._supported_radio_group((question_text or "").lower()):
                return

            target = self._resolve_option_choice(
                question_text,
                question_text,
                option_texts,
                resume_summary,
                cover_letter,
            )

            chosen = None
            if target:
                for radio, label_text, value in radio_details:
                    if target.lower() == label_text or target.lower() == value:
                        chosen = radio
                        break

            (chosen or radios[0]).click(force=True)
            self.log.info(f"Answered radio question: {question_text or 'unnamed radio group'}")
            self.human_pause(0.3)

        # Pass 1: fieldset-based radio groups.
        for fs in page.locator("fieldset:visible").all():
            try:
                legend = (fs.locator("legend").text_content() or "").strip()
                radios = fs.locator("input[type='radio']").all()
                _answer_group(legend, radios)
            except Exception:
                continue

        # Pass 2: radio groups outside fieldsets, grouped by name.
        groups: dict[str, list] = {}
        for radio in page.locator("input[type='radio']:visible").all():
            try:
                if radio.is_checked():
                    continue
                name = (radio.get_attribute("name") or "").strip()
                if not name:
                    rid = (radio.get_attribute("id") or "").strip()
                    name = f"id::{rid}" if rid else "ungrouped"
                groups.setdefault(name, []).append(radio)
            except Exception:
                continue

        for group_name, radios in groups.items():
            if len(radios) < 2:
                continue
            try:
                q_text = ""
                first_radio = radios[0]
                rid = first_radio.get_attribute("id") or ""
                if rid:
                    label = page.locator(f"label[for='{rid}']")
                    if label.count() > 0:
                        q_text = (label.first.text_content() or "").strip()
                attrs = self._normalise_attrs(first_radio)
                merged_question = " ".join([q_text, attrs, group_name]).strip()
                _answer_group(merged_question, radios)
            except Exception:
                continue

    def _force_answer_required_radios(self, page: Locator, resume_summary: str, cover_letter: str) -> None:
        """Final sweep: ensure every visible radio group has a selection."""
        groups: dict[str, list] = {}
        for radio in page.locator("input[type='radio']:visible").all():
            try:
                name = (radio.get_attribute("name") or "").strip()
                if not name:
                    rid = (radio.get_attribute("id") or "").strip()
                    name = f"id::{rid}" if rid else "ungrouped"
                groups.setdefault(name, []).append(radio)
            except Exception:
                continue

        for group_name, radios in groups.items():
            try:
                if len(radios) < 2:
                    continue
                if any(r.is_checked() for r in radios):
                    continue

                option_texts: list[str] = []
                radio_map = []
                q_text_parts: list[str] = [group_name]
                for radio in radios:
                    radio_id = (radio.get_attribute("id") or "").strip()
                    label_text = ""
                    if radio_id:
                        label = page.locator(f"label[for='{radio_id}']")
                        if label.count() > 0:
                            label_text = (label.first.text_content() or "").strip()
                    value = (radio.get_attribute("value") or "").strip()
                    text = label_text or value or "option"
                    option_texts.append(text)
                    radio_map.append((radio, text.lower(), value.lower()))
                    if label_text:
                        q_text_parts.append(label_text)

                question_text = " ".join(q_text_parts).strip()
                target = self._resolve_option_choice(
                    question_text,
                    question_text,
                    option_texts,
                    resume_summary,
                    cover_letter,
                )

                lowered_options = [o.lower() for o in option_texts]
                yes_no_group = ("yes" in lowered_options and "no" in lowered_options)
                if not target and yes_no_group:
                    target = "Yes"
                if not target and option_texts:
                    target = option_texts[0]

                chosen = None
                if target:
                    for radio, label_lower, value_lower in radio_map:
                        t = target.lower()
                        if t == label_lower or t == value_lower or t in label_lower:
                            chosen = radio
                            break

                (chosen or radios[0]).click(force=True)
                self.log.info(f"Forced radio selection for group: {group_name}")
                self.human_pause(0.2)
            except Exception:
                continue
    def _fill_checkboxes(self, page: Locator, resume_summary: str, cover_letter: str) -> None:
        """Fill visible unchecked checkboxes with best-effort answers."""
        profile = self._extract_resume_profile(resume_summary, cover_letter)
        for checkbox in page.locator("input[type='checkbox']:visible").all():
            try:
                if checkbox.is_checked():
                    continue
                attrs = self._normalise_attrs(checkbox)
                question_text = self._extract_question_text(checkbox)
                prompt_text = f"{question_text} {attrs}".strip().lower()

                # Accept common consent/acknowledgement boxes, avoid opting into marketing by default.
                should_check = None
                if any(token in prompt_text for token in ["currently work here", "current role", "present role", "still working"]):
                    should_check = profile.get("currently_work_here", "yes") == "yes"
                elif any(token in prompt_text for token in ["terms", "privacy", "consent", "agree", "certify", "acknowledge"]):
                    should_check = True
                elif any(token in prompt_text for token in ["sms", "whatsapp", "marketing", "newsletter", "promotional", "job alert"]):
                    should_check = False
                else:
                    llm_choice = self._answer_free_text_with_llm(
                        question_text or attrs or "Should this checkbox be checked?",
                        resume_summary,
                        cover_letter,
                        max_chars=10,
                    ).lower()
                    should_check = any(token in llm_choice for token in ["yes", "check", "true"])

                if should_check:
                    checkbox.check(force=True)
                    self.log.info(f"Checked checkbox: {question_text or attrs or 'unnamed checkbox'}")
                    self.human_pause(0.2)
            except Exception:
                pass

    def _is_already_applied(self, page: Page) -> bool:
        """Check for a real LinkedIn applied-state indicator near the apply action."""
        applied_badges = [
            ".jobs-s-apply--posted",
            "button[aria-label*='Applied']",
            "span.jobs-apply-button--top-card:has-text('Applied')",
            "div.jobs-apply-button--top-card:has-text('Applied')",
        ]
        for selector in applied_badges:
            try:
                badge = page.locator(selector).first
                if badge.count() > 0 and badge.is_visible():
                    return True
            except Exception:
                continue
        return False


    def apply_linkedin(
        self,
        page: Page,
        job: JobListing,
        cover_letter: str,
        resume_summary: str = "",
    ) -> SubmitResult:
        """Attempt only a simple one-step Easy Apply flow."""
        self._last_result_notes = ""
        self.log.info(f"Opening LinkedIn job: {job.url}")
        try:
            page.goto(job.url, wait_until="networkidle", timeout=45_000)
        except Exception:
            page.goto(job.url, wait_until="domcontentloaded", timeout=40_000)
        self.human_pause(2.0)

        page.mouse.wheel(0, 400)
        self.human_pause(1.0)

        if self._is_already_applied(page):
            self.log.info(f"Already applied to: {job.title} - skipping")
            return SubmitResult.SKIPPED

        apply_kind, apply_button = self._get_apply_button(page)
        if apply_button is None:
            self.log.warning(f"No Apply or Easy Apply button for: {job.title} (page: {page.url[:80]})")
            return SubmitResult.SKIPPED

        if apply_kind == "external":
            original_url = page.url
            new_page = None
            if self._browser is not None:
                try:
                    with self._browser.expect_page(timeout=5_000) as new_page_info:
                        apply_button.click()
                    new_page = new_page_info.value
                except Exception:
                    apply_button.click()
            else:
                apply_button.click()
            self.human_pause()
            self.log.info(f"Clicked Apply for: {job.title}")

            target_page = new_page or page
            try:
                target_page.wait_for_load_state("domcontentloaded", timeout=10_000)
            except Exception:
                pass
            if target_page is page and page.url == original_url:
                self.log.warning(f"Apply button did not navigate for: {job.title}")
                return SubmitResult.SKIPPED
            return self._apply_external_flow(
                target_page,
                job,
                cover_letter,
                resume_summary,
            )

        apply_button.click()
        self.human_pause()
        self.log.info(f"Clicked Easy Apply for: {job.title}")

        modal = self._get_easy_apply_modal(page)
        if modal is None:
            self.log.warning(f"Easy Apply modal did not open for: {job.title}")
            return SubmitResult.SKIPPED

        cover_letter = self._generate_cover_letter_if_needed(
            modal,
            job,
            cover_letter,
            resume_summary,
        )

        max_steps = 12
        for step in range(1, max_steps + 1):
            modal = self._get_easy_apply_modal(page)
            if modal is None:
                self.log.warning(f"Easy Apply modal closed unexpectedly for: {job.title}")
                return SubmitResult.FAILED

            self.log.info(f"Processing Easy Apply step {step} for: {job.title}")
            self._upload_resume(modal)

            cover_letter = self._generate_cover_letter_if_needed(
                modal,
                job,
                cover_letter,
                resume_summary,
            )
            self._fill_text_inputs(modal, resume_summary, cover_letter)
            self._fill_textareas(modal, cover_letter, resume_summary)
            self._fill_dropdowns(modal, resume_summary, cover_letter)
            self._fill_comboboxes(modal, resume_summary, cover_letter)
            self._fill_radios(modal, resume_summary, cover_letter)
            self._fill_checkboxes(modal, resume_summary, cover_letter)

            action_type, action_button = self._get_primary_action(modal)
            if action_button is None:
                self.log.info(f"Skipping {job.title} because no Easy Apply action button is available.")
                self._close_easy_apply_modal(page)
                return SubmitResult.SKIPPED

            if action_type == "submit":
                if self.dry_run:
                    self._last_result_notes = "Dry run stopped before submit."
                    self.log.info(f"DRY RUN - Easy Apply is ready for submit on step {step}: {job.title}")
                    self._close_easy_apply_modal(page)
                    return SubmitResult.DRY_RUN

                success, errors = self._attempt_action_with_repair(
                    action_button,
                    action_type,
                    page,
                    modal,
                    job,
                    resume_summary,
                    cover_letter,
                )
                if not success:
                    debug_path = self._save_debug_snapshot(page, job, f"step_{step}_validation")
                    note_parts = [f"Easy Apply validation errors: {' | '.join(errors[:3])}"]
                    if debug_path:
                        note_parts.append(f"Screenshot: {debug_path}")
                    self._last_result_notes = " ".join(note_parts)
                    return SubmitResult.FAILED
                return self._wait_for_submission_outcome(page, job)

            success, errors = self._attempt_action_with_repair(
                action_button,
                action_type,
                page,
                modal,
                job,
                resume_summary,
                cover_letter,
            )
            if not success:
                debug_path = self._save_debug_snapshot(page, job, f"step_{step}_validation")
                note_parts = [f"Easy Apply step validation errors: {' | '.join(errors[:3])}"]
                if debug_path:
                    note_parts.append(f"Screenshot: {debug_path}")
                self._last_result_notes = " ".join(note_parts)
                return SubmitResult.FAILED
            self.log.info(f"Advanced Easy Apply via {action_type} on step {step}")
            self.human_pause(1.5)

        debug_path = self._save_debug_snapshot(page, job, "easy_apply_step_limit")
        note_parts = [f"Easy Apply flow exceeded {max_steps} steps."]
        if debug_path:
            note_parts.append(f"Screenshot: {debug_path}")
        self._last_result_notes = " ".join(note_parts)
        self.log.warning(f"Easy Apply exceeded {max_steps} steps for: {job.title}")
        self._close_easy_apply_modal(page)
        return SubmitResult.FAILED

    def run(
        self,
        jobs: list[JobListing],
        cover_letters: dict[str, str],
        resume_summary: str = "",
        applied_ids: set[str] | None = None,
    ) -> list[ApplicationResult]:
        """Apply to approved jobs, skipping duplicates and unsupported flows."""
        results = []
        context = self.start_browser()
        known_applied_ids = set(applied_ids or set())
        attempted_job_ids: set[str] = set()

        try:
            page = context.new_page()
            try:
                page.bring_to_front()
            except Exception:
                pass
            applied_count = 0

            for job in jobs:
                if applied_count >= self.max_applications:
                    self.log.info(
                        f"Reached max applications per run={self.max_applications}. Stopping."
                    )
                    break

                if job.job_id in known_applied_ids:
                    self.log.info(f"Skipping duplicate applied job: {job.title} [{job.job_id}]")
                    results.append(
                        ApplicationResult(
                            job=job,
                            result=SubmitResult.SKIPPED,
                            notes="Skipped because this job was already recorded as applied.",
                        )
                    )
                    continue

                if job.job_id in attempted_job_ids:
                    self.log.info(f"Skipping duplicate job within this run: {job.title} [{job.job_id}]")
                    results.append(
                        ApplicationResult(
                            job=job,
                            result=SubmitResult.SKIPPED,
                            notes="Skipped because this job was already attempted in the current run.",
                        )
                    )
                    continue

                attempted_job_ids.add(job.job_id)
                cover_letter = cover_letters.get(job.job_id, "")
                self._last_result_notes = ""
                self.log_for_job(
                    "info",
                    job.job_id,
                    f"Applying: {job.title} @ {job.company} [{job.platform}]",
                )

                try:
                    if job.platform == "linkedin":
                        result = self.apply_linkedin(
                            page,
                            job,
                            cover_letter,
                            resume_summary=resume_summary,
                        )
                    else:
                        self.log.warning(f"Unknown platform: {job.platform}")
                        self._last_result_notes = f"Skipped because platform '{job.platform}' is not supported."
                        result = SubmitResult.SKIPPED
                except Exception as e:
                    self.log.error(f"Error applying to {job.title}: {e}")
                    structured = SubmissionError(
                        stage="submission",
                        code="job_apply_failed",
                        message=str(e),
                        retriable=True,
                        details={"job_id": job.job_id, "job_url": job.url},
                    )
                    self._last_result_notes = str(structured)
                    result = SubmitResult.FAILED

                note = (self._last_result_notes or "").strip()
                if not note:
                    if result == SubmitResult.SKIPPED:
                        note = "Skipped by submission flow. No actionable apply state was detected."
                    elif result == SubmitResult.FAILED:
                        note = "Submission failed without a captured validation reason."
                    elif result == SubmitResult.APPLIED:
                        note = "Submission completed and apply state was detected."
                    elif result == SubmitResult.DRY_RUN:
                        note = "Dry run completed before final submit."

                results.append(
                    ApplicationResult(
                        job=job,
                        result=result,
                        notes=note,
                    )
                )

                if result in (SubmitResult.APPLIED, SubmitResult.DRY_RUN):
                    applied_count += 1
                    known_applied_ids.add(job.job_id)

                self.human_pause(2.0)
        finally:
            self.stop_browser()

        self.log.info(f"Submission complete. {applied_count} applications attempted.")
        return results












