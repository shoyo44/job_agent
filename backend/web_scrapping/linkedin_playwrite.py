"""
linkedin_playwright.py
-----------------------
Scrapes LinkedIn job listings using Playwright.
Handles login, search, pagination, and job detail extraction.
Strategy: USE PLAYWRIGHT for authenticated search with Easy Apply filter.

Anti-ban delay strategy
-----------------------
Every action that touches the network or clicks a UI element uses a
randomised delay drawn from [min_delay, max_delay] seconds.
Pass a DelayConfig to the constructor (or use the .env HUMAN_DELAY_MS
default) to tune aggressiveness vs. safety.
"""

import random
import re
import sys
import time
import os
import shutil
import tempfile
from dataclasses import dataclass
from typing import Optional
from urllib.parse import quote_plus

from playwright.sync_api import sync_playwright, Page, BrowserContext

import config
from agent.base_agent import _setup_logger
from agent.errors import ScraperError
from agent.planner_agent import JobListing
from tools.job_tools import (
    make_job_id, normalise_work_mode, normalise_salary,
    parse_date_posted, clean_description, is_too_old,
)


LINKEDIN_BASE = "https://www.linkedin.com"
LINKEDIN_JOBS = "https://www.linkedin.com/jobs/search/"
ROLE_ALIASES = {
    "machine learning engineer": {
        "machine learning engineer",
        "ml engineer",
        "machine learning developer",
        "ml developer",
        "mlops engineer",
    },
    "ai engineer": {
        "ai engineer",
        "artificial intelligence engineer",
        "generative ai engineer",
        "llm engineer",
    },
    "data scientist": {
        "data scientist",
        "applied scientist",
        "ml scientist",
        "machine learning scientist",
    },
    "data engineer": {
        "data engineer",
        "machine learning data engineer",
    },
}


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


# ------------------------------------------------------------------
# Delay configuration
# ------------------------------------------------------------------
@dataclass
class DelayConfig:
    """
    Controls how long the scraper pauses between actions.
    All values are in seconds.

    Presets (use the class methods):
      DelayConfig.safe()       — slow but very unlikely to be banned
      DelayConfig.balanced()   — good default (recommended)
      DelayConfig.fast()       — faster, slightly higher risk

    Or pass custom values directly.
    """
    page_load_min: float = 2.5      # After navigating to a new URL
    page_load_max: float = 5.0
    action_min: float = 0.8         # Between individual UI actions (click/fill)
    action_max: float = 2.0
    between_pages_min: float = 3.0  # Between search result pages
    between_pages_max: float = 7.0
    between_cards_min: float = 0.3  # Between processing each job card
    between_cards_max: float = 0.8
    scroll_min: float = 0.5         # Between scroll steps
    scroll_max: float = 1.2

    @classmethod
    def safe(cls) -> "DelayConfig":
        """Very conservative — mimics a slow, careful human reader."""
        return cls(
            page_load_min=4.0, page_load_max=8.0,
            action_min=1.5, action_max=3.5,
            between_pages_min=6.0, between_pages_max=12.0,
            between_cards_min=0.5, between_cards_max=1.5,
            scroll_min=1.0, scroll_max=2.0,
        )

    @classmethod
    def balanced(cls) -> "DelayConfig":
        """Default — good balance between speed and stealth."""
        return cls()  # uses the dataclass defaults above

    @classmethod
    def fast(cls) -> "DelayConfig":
        """Faster scraping — higher ban risk on aggressive sites."""
        return cls(
            page_load_min=1.2, page_load_max=2.5,
            action_min=0.3, action_max=0.8,
            between_pages_min=1.5, between_pages_max=3.0,
            between_cards_min=0.1, between_cards_max=0.3,
            scroll_min=0.2, scroll_max=0.5,
        )

    def sleep_page_load(self) -> None:
        time.sleep(random.uniform(self.page_load_min, self.page_load_max))

    def sleep_action(self) -> None:
        time.sleep(random.uniform(self.action_min, self.action_max))

    def sleep_between_pages(self) -> None:
        time.sleep(random.uniform(self.between_pages_min, self.between_pages_max))

    def sleep_between_cards(self) -> None:
        time.sleep(random.uniform(self.between_cards_min, self.between_cards_max))

    def sleep_scroll(self) -> None:
        time.sleep(random.uniform(self.scroll_min, self.scroll_max))


# ------------------------------------------------------------------
# Scraper
# ------------------------------------------------------------------
class LinkedInPlaywrightScraper:
    """
    Playwright-based LinkedIn job scraper.
    Uses a persistent browser context to preserve sessions between runs.

    Args:
        delay: DelayConfig instance controlling anti-ban pacing.
               Defaults to DelayConfig.balanced().
               Can also be set per-query via scrape(query={..., "delay": "safe"}).
    """

    def __init__(self, delay: DelayConfig = None, run_id: str = "-"):
        self._playwright = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._detail_page: Optional[Page] = None
        self.delay = delay or DelayConfig.balanced()
        self.run_id = run_id
        self.log = _setup_logger("LinkedInScraper", run_id=run_id)
        self.max_cards_per_page = 32
        self._temp_profile_dir: str | None = None

    # ------------------------------------------------------------------
    # Browser lifecycle
    # ------------------------------------------------------------------
    def _prepare_user_data_dir(self, force_temp_profile: bool = False) -> str:
        if config.RUNTIME_BROWSER_PROFILE_DIR:
            user_data_dir = config.RUNTIME_BROWSER_PROFILE_DIR
            os.makedirs(user_data_dir, exist_ok=True)
            self.log.info(f"Using shared runtime browser profile: {user_data_dir}")
        elif force_temp_profile or config.USE_TEMP_BROWSER_PROFILE:
            if not self._temp_profile_dir:
                self._temp_profile_dir = tempfile.mkdtemp(prefix="job-agent-chromium-")
            user_data_dir = self._temp_profile_dir
            self.log.info(f"Using temporary browser profile: {user_data_dir}")
        else:
            user_data_dir = "chromium/user_data"
            os.makedirs(user_data_dir, exist_ok=True)

        lock_file = os.path.join(user_data_dir, "SingletonLock")
        if os.path.exists(lock_file):
            os.remove(lock_file)
            self.log.info("Removed stale SingletonLock and continued with saved session.")

        return user_data_dir

    def _launch_context(self, user_data_dir: str) -> None:
        launch_kwargs = dict(
            user_data_dir=user_data_dir,
            headless=config.HEADLESS,
            ignore_https_errors=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-infobars",
                "--start-maximized",
            ],
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            no_viewport=True,
        )
        if config.CHROMIUM_PATH:
            launch_kwargs["executable_path"] = config.CHROMIUM_PATH
            self.log.info(f"Using local Chromium: {config.CHROMIUM_PATH}")
        else:
            self.log.info("Using Playwright bundled Chromium.")

        self._context = self._playwright.chromium.launch_persistent_context(**launch_kwargs)
        self._page = self._context.new_page()
        self._detail_page = self._context.new_page()
        self._page.bring_to_front()
        self._page.goto("about:blank")

    def start(self) -> None:
        try:
            _assert_playwright_start_supported()
            # Protect Playwright driver process from low default heap on long runs.
            if "NODE_OPTIONS" not in os.environ:
                os.environ["NODE_OPTIONS"] = "--max-old-space-size=2048"
            self._playwright = sync_playwright().start()
            user_data_dir = self._prepare_user_data_dir(force_temp_profile=False)
            try:
                self._launch_context(user_data_dir)
            except Exception as launch_error:
                if not config.USE_TEMP_BROWSER_PROFILE:
                    self.log.warning(
                        "Persistent profile launch failed; retrying with a temporary browser profile: "
                        f"{launch_error}"
                    )
                    user_data_dir = self._prepare_user_data_dir(force_temp_profile=True)
                    self._launch_context(user_data_dir)
                else:
                    raise
        except Exception as e:
            raise ScraperError(
                stage="scraper_start",
                code="linkedin_start_failed",
                message=str(e),
                retriable=True,
                details={"run_id": self.run_id},
            ) from e

    def stop(self) -> None:
        if self._detail_page:
            self._detail_page.close()
        if self._context:
            self._context.close()
        if self._playwright:
            self._playwright.stop()
        if self._temp_profile_dir:
            try:
                shutil.rmtree(self._temp_profile_dir, ignore_errors=True)
            except Exception:
                pass
            self._temp_profile_dir = None

    # ------------------------------------------------------------------
    # Human-like scrolling
    # ------------------------------------------------------------------
    def _scroll_down_slowly(self, steps: int = 4) -> None:
        """
        Scrolls the page down in small increments to simulate a human
        reading the results before the scraper extracts the cards.
        """
        for _ in range(steps):
            self._page.mouse.wheel(0, random.randint(300, 600))
            self.delay.sleep_scroll()

    def _ensure_detail_page(self) -> Optional[Page]:
        """Recreate the detail page if LinkedIn or the browser closed it."""
        if not self._context:
            return None
        try:
            if self._detail_page and not self._detail_page.is_closed():
                return self._detail_page
        except Exception:
            pass

        try:
            self._detail_page = self._context.new_page()
            return self._detail_page
        except Exception:
            self._detail_page = None
            return None
    def _build_keyword_query(self, role: str, keywords: list[str] | None) -> str:
        """Build a query centered on the exact requested role to reduce noise."""
        role_clean = re.sub(r"\s+", " ", (role or "").strip())
        extras: list[str] = []
        for term in (keywords or []):
            token = re.sub(r"\s+", " ", (term or "").strip())
            if not token:
                continue
            token_lower = token.lower()
            if token_lower in {"ai", "ml", "data", "engineer"}:
                continue
            extras.append(token)

        # Keep exact role phrase first; add at most two specific extras.
        query_parts = [f'"{role_clean}"']
        query_parts.extend(extras[:2])
        return " ".join(query_parts).strip()

    def _title_relevance_score(self, title: str, role: str, keywords: list[str] | None = None) -> int:
        title_lower = (title or "").lower()
        title_tokens = set(re.findall(r"[a-z0-9]+", title_lower))
        role_lower = (role or "").lower()
        role_tokens = set(re.findall(r"[a-z0-9]+", role_lower))
        stop_words = {
            "and", "or", "the", "a", "an", "senior", "junior", "lead",
            "staff", "principal", "associate", "intern",
        }
        role_tokens = {token for token in role_tokens if token not in stop_words}

        alias_candidates = {role_lower}
        for canonical_role, aliases in ROLE_ALIASES.items():
            if role_lower == canonical_role or role_lower in aliases:
                alias_candidates |= aliases
                alias_candidates.add(canonical_role)

        score = 0
        if any(alias in title_lower for alias in alias_candidates):
            score += 3

        if "generative ai" in role_lower or "gen ai" in role_lower:
            if any(token in title_lower for token in ["generative", "llm", "rag", "agentic", "ai"]):
                score += 2

        overlap = title_tokens & role_tokens
        if len(overlap) >= 2:
            score += 2
        elif len(overlap) == 1:
            score += 1

        keyword_tokens = set()
        for keyword in keywords or []:
            keyword_tokens.update(re.findall(r"[a-z0-9]+", keyword.lower()))
        if title_tokens & keyword_tokens:
            score += 1

        if "engineer" in role_tokens and "engineer" in title_tokens:
            score += 1
        if "scientist" in role_tokens and "scientist" in title_tokens:
            score += 1

        return score

    def _contains_hard_negative(self, title_lower: str, role_lower: str) -> bool:
        """Reject clearly unrelated role families early."""
        common_negative = [
            "backend developer",
            "front end",
            "frontend",
            "full stack",
            "mobile developer",
            "android",
            "ios",
            "qa engineer",
            "test engineer",
            "devops",
            "sre",
            "product manager",
            "ui ux",
            "designer",
            "sales",
            "recruiter",
        ]

        if any(token in title_lower for token in common_negative):
            if "data engineer" in role_lower and "data" in title_lower and "engineer" in title_lower:
                return False
            return True

        if "data engineer" in role_lower and any(token in title_lower for token in ["data scientist", "scientist"]):
            return True
        if "data scientist" in role_lower and any(token in title_lower for token in ["data engineer", "etl engineer"]):
            return True
        return False

    def _is_relevant_title(self, title: str, role: str, keywords: list[str] = None) -> bool:
        """Role-family-aware title filter to keep precision high."""
        title_lower = (title or "").lower()
        role_lower = (role or "").lower()

        if self._contains_hard_negative(title_lower, role_lower):
            return False

        # Family-specific hard guards.
        if "data engineer" in role_lower:
            if "data" not in title_lower:
                return False
            if not any(token in title_lower for token in ["engineer", "etl", "pipeline", "platform", "analytics"]):
                return False
        elif "data scientist" in role_lower:
            if not any(token in title_lower for token in ["scientist", "data science", "ml scientist", "applied scientist"]):
                return False
        elif "machine learning engineer" in role_lower or role_lower.startswith("ml engineer"):
            if not any(token in title_lower for token in ["machine learning", "ml", "mlops"]):
                return False
            if not any(token in title_lower for token in ["engineer", "developer", "architect"]):
                return False
        elif "generative ai" in role_lower or "gen ai" in role_lower:
            if not any(token in title_lower for token in ["generative", "llm", "rag", "agentic"]):
                return False
        elif "ai engineer" in role_lower:
            if not any(token in title_lower for token in ["ai", "artificial intelligence", "llm", "generative", "agentic"]):
                return False

        score = self._title_relevance_score(title, role, keywords)
        return score >= 2

    def _is_promoted_card(self, card) -> bool:
        """Best-effort check for sponsored/promoted result cards."""
        try:
            text = (card.inner_text() or "").lower()
        except Exception:
            return False
        return "promoted" in text

    # ------------------------------------------------------------------
    # Login
    # ------------------------------------------------------------------
    def _is_logged_in(self) -> bool:
        """Returns True if a LinkedIn session is already active."""
        try:
            self._page.goto(LINKEDIN_BASE, wait_until="domcontentloaded", timeout=30_000)
            # Give the redirect to /feed time to complete
            self.delay.sleep_page_load()
            # Check URL and visible page elements
            url = self._page.url
            if "feed" in url or "mynetwork" in url or "jobs" in url:
                return True
            # Sometimes LinkedIn lands on the homepage itself when logged in
            nav = self._page.query_selector("nav[aria-label='Global'], .global-nav")
            return nav is not None
        except Exception:
            return False

    def login(self) -> bool:
        """
        Logs into LinkedIn. Skips if an existing session is detected.
        Returns True on success.
        """
        if self._is_logged_in():
            self.log.info("Session already active, skipping login.")
            return True

        self._page.goto(f"{LINKEDIN_BASE}/login", wait_until="domcontentloaded", timeout=30_000)
        self.delay.sleep_page_load()

        if self._page.locator("#username").count() > 0:
            email_selector = "#username"
            password_selector = "#password"
        elif self._page.locator("#session_key").count() > 0:
            email_selector = "#session_key"
            password_selector = "#session_password"
        else:
            self.log.warning("Could not find login fields.")
            return False

        # Type email character-by-character for human-like behaviour
        self._page.click(email_selector)
        self.delay.sleep_action()
        self._page.type(email_selector, config.LINKEDIN_EMAIL, delay=80)

        self.delay.sleep_action()

        self._page.click(password_selector)
        self.delay.sleep_action()
        self._page.type(password_selector, config.LINKEDIN_PASSWORD, delay=80)

        self.delay.sleep_action()
        self._page.click("button[type='submit']")
        self._page.wait_for_url("**/feed**", timeout=20_000)

        if "feed" in self._page.url:
            self.log.info("Login successful.")
            self.delay.sleep_page_load()
            return True

        self.log.warning("Login may have failed, check for CAPTCHA.")
        return False

    # ------------------------------------------------------------------
    # Job search
    # ------------------------------------------------------------------
    def search_jobs(
        self,
        role: str,
        location: str,
        keywords: list[str] = None,
        easy_apply_only: bool = True,
        max_pages: int = 3,
        max_days_old: int = 30,
        max_jobs: int = 10,
        enrich_details: bool = False,
    ) -> list[JobListing]:
        """
        Searches LinkedIn for jobs and returns unscored JobListing objects.

        Args:
            role           : Primary job title to search.
            location       : City name (e.g. "Bangalore").
            keywords       : Extra search keywords appended to the role.
            easy_apply_only: If True, adds LinkedIn's Easy Apply filter.
            max_pages      : Max result pages to scrape per query.
            max_days_old   : Filter out listings older than this many days.
            max_jobs       : Maximum number of jobs to collect for this query.
        """
        jobs: list[JobListing] = []
        fallback_candidates: list[JobListing] = []
        keyword_str = self._build_keyword_query(role, keywords)

        for page_num in range(max_pages):
            dropped_parse = 0
            dropped_old = 0
            dropped_irrelevant = 0
            dropped_promoted = 0
            start = page_num * 25
            url = (
                f"{LINKEDIN_JOBS}?keywords={quote_plus(keyword_str)}"
                f"&location={quote_plus(location)}"
                f"&start={start}"
            )
            if easy_apply_only:
                url += "&f_LF=f_AL"

            self.log.info(
                f"Page {page_num + 1}/{max_pages} | role={role} location={location}"
            )
            self._page.goto(url, wait_until="domcontentloaded", timeout=40_000)
            self.delay.sleep_page_load()

            # Scroll to trigger lazy loading of job cards
            self._scroll_down_slowly(steps=random.randint(3, 6))

            job_cards = self._page.query_selector_all(
                # Authenticated job search selectors (logged-in LinkedIn)
                "li.jobs-search-results__list-item, "
                "div.job-card-container, "
                "li.scaffold-layout__list-item"
            )
            self.log.info(f"Found {len(job_cards)} cards on page {page_num + 1}")

            if not job_cards:
                # Fallback: try public selectors
                job_cards = self._page.query_selector_all(
                    ".job-search-card, .base-card"
                )
                self.log.info(f"Fallback selector found {len(job_cards)} cards")

            for i, card in enumerate(job_cards[: self.max_cards_per_page]):
                try:
                    if self._is_promoted_card(card):
                        dropped_promoted += 1
                        continue

                    job = self._extract_card(card)
                    if not job:
                        dropped_parse += 1
                        continue

                    if is_too_old(job.date_posted, max_days=max_days_old):
                        dropped_old += 1
                        continue

                    relevance_score = self._title_relevance_score(job.title, role, keywords)
                    if not self._is_relevant_title(job.title, role, keywords):
                        dropped_irrelevant += 1
                        # Keep only near-miss titles for fallback; drop clear mismatches.
                        if relevance_score == 1 and len(fallback_candidates) < max_jobs:
                            fallback_candidates.append(job)
                        continue

                    # Full detail-page enrichment is expensive; keep it opt-in to avoid OOM.
                    if enrich_details:
                        job = self._fetch_job_details(job)
                    jobs.append(job)
                    if len(jobs) >= max_jobs:
                        self.log.info(f"Reached max_jobs={max_jobs} for this query.")
                        return jobs
                except Exception as e:
                    self.log.warning(f"Card {i} error: {e}")
                # Small pause between processing each card
                self.delay.sleep_between_cards()

            self.log.info(
                "Page filter summary: "
                f"kept={len(jobs)} "
                f"dropped_parse={dropped_parse} "
                f"dropped_old={dropped_old} "
                f"dropped_irrelevant={dropped_irrelevant} "
                f"dropped_promoted={dropped_promoted}"
            )

            # Check next page
            next_btn = self._page.query_selector("button[aria-label='Next']")
            if not next_btn or not next_btn.is_visible():
                self.log.info("No more pages.")
                break

            # Longer pause between pages to look human
            wait = random.uniform(
                self.delay.between_pages_min,
                self.delay.between_pages_max,
            )
            self.log.info(f"Waiting {wait:.1f}s before next page...")
            time.sleep(wait)

        if not jobs and fallback_candidates:
            self.log.warning(
                "No jobs passed relevance filter; returning fallback parsed cards "
                f"({len(fallback_candidates)} candidates)."
            )
            jobs = fallback_candidates[:max_jobs]
        elif len(jobs) < max(2, min(4, max_jobs // 3)) and fallback_candidates:
            needed = max_jobs - len(jobs)
            if needed > 0:
                self.log.info(
                    f"Low kept jobs ({len(jobs)}). Backfilling up to {min(needed, len(fallback_candidates))} fallback cards."
                )
                jobs.extend(fallback_candidates[:needed])

        self.log.info(f"Total jobs scraped: {len(jobs)}")
        return jobs[:max_jobs]

    def _fetch_job_details(self, job: JobListing) -> JobListing:
        """
        Enriches a job listing by loading the LinkedIn detail page in a
        separate tab and extracting a fuller description.
        """
        detail_page = self._ensure_detail_page()
        if not detail_page or not job.url:
            return job

        try:
            detail_page.goto(job.url, wait_until="domcontentloaded", timeout=30_000)
            self.delay.sleep_action()

            show_more = detail_page.locator(
                "button.jobs-description__footer-button, "
                "button[aria-label*='Click to see more description']"
            ).first
            if show_more.count() > 0:
                try:
                    show_more.click()
                    self.delay.sleep_action()
                except Exception:
                    pass

            description_selectors = [
                ".jobs-description__content",
                ".jobs-description-content__text",
                "#job-details",
                ".jobs-box__html-content",
                "main",
                "article",
            ]
            for selector in description_selectors:
                block = detail_page.locator(selector).first
                if block.count() == 0:
                    continue
                text = (block.inner_text(timeout=2_000) or "").strip()
                if len(text) >= 80:
                    job.description = clean_description(text)
                    break

            salary_selectors = [
                ".job-details-jobs-unified-top-card__primary-description-container",
                ".job-details-fit-level-preferences",
                ".jobs-unified-top-card__job-insight",
            ]
            for selector in salary_selectors:
                block = detail_page.locator(selector).first
                if block.count() == 0:
                    continue
                text = (block.inner_text(timeout=2_000) or "").strip()
                if text:
                    job.salary = normalise_salary(text)
                    break
        except Exception as e:
            self.log.warning(f"Detail fetch error for {job.title}: {e}")
            try:
                if detail_page.is_closed():
                    self._detail_page = None
            except Exception:
                self._detail_page = None

        return job

    # ------------------------------------------------------------------
    # Card extraction
    # ------------------------------------------------------------------
    def _extract_card(self, card) -> Optional[JobListing]:
        """Extracts job data from a LinkedIn job card element (authenticated view)."""
        # Authenticated selectors (logged-in job search)
        title_el   = card.query_selector(
            "a.job-card-container__link span[aria-hidden], "
            "h3.job-card-list__title, "
            "h3.base-search-card__title, "
            ".job-search-card__title"
        )
        company_el = card.query_selector(
            "h4.job-card-container__company-name, "
            "span.job-card-container__primary-description, "
            "h4.base-search-card__subtitle, "
            ".job-search-card__company-name"
        )
        loc_el     = card.query_selector(
            "li.job-card-container__metadata-wrapper, "
            "span.job-card-container__metadata-item, "
            ".job-search-card__location"
        )
        link_el    = card.query_selector(
            "a.job-card-container__link, "
            "a.base-card__full-link, "
            "a[href*='/jobs/view/']"
        )
        date_el    = card.query_selector(
            "time, "
            "span.job-card-container__listdate, "
            ".job-search-card__listdate"
        )
        desc_el    = card.query_selector(
            ".job-card-list__description-snippet, "
            ".job-search-card__snippet, "
            ".job-card-container__snippet"
        )

        if not title_el:
            title_el = card.query_selector(
                "a[href*='/jobs/view/'] span[aria-hidden], "
                "a[href*='/jobs/view/'] strong, "
                "a[href*='/jobs/view/']"
            )
        if not link_el:
            link_el = card.query_selector("a[href*='/jobs/view/']")

        if not title_el or not link_el:
            return None

        title = (title_el.inner_text() or "").strip()
        if not title:
            title = (link_el.get_attribute("aria-label") or "").strip()
        if not title:
            return None

        company      = company_el.inner_text().strip() if company_el else "Unknown"
        location_raw = loc_el.inner_text().strip() if loc_el else ""
        description_snippet = (desc_el.inner_text().strip() if desc_el else "")
        url          = link_el.get_attribute("href") or ""
        if url and not url.startswith("http"):
            url = LINKEDIN_BASE + url
        # date_el can be None on some cards — guard carefully
        if date_el:
            date_raw = date_el.get_attribute("datetime") or date_el.inner_text().strip()
        else:
            date_raw = ""

        return JobListing(
            job_id      = make_job_id("linkedin", company, title, url),
            platform    = "linkedin",
            title       = title,
            company     = company,
            location    = location_raw,
            work_mode   = normalise_work_mode(location_raw + " " + title),
            salary      = "Not specified",
            description = clean_description(description_snippet),
            url         = url,
            date_posted = parse_date_posted(date_raw),
        )

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------
    def scrape(self, query: dict) -> list[JobListing]:
        """
        Public entry point.

        query dict keys:
          role, location, keywords, easy_apply_only, max_pages, max_days_old,
          delay  — optional preset name: "safe" | "balanced" | "fast"

        Example:
          scraper.scrape({"role": "AI Engineer", "location": "Bangalore", "delay": "safe"})
        """
        # Allow per-query delay override
        delay_preset = query.get("delay", "balanced")
        if delay_preset == "safe":
            self.delay = DelayConfig.safe()
        elif delay_preset == "fast":
            self.delay = DelayConfig.fast()
        else:
            self.delay = DelayConfig.balanced()

        self.start()
        try:
            if not self.login():
                self.log.warning("Could not login. Skipping LinkedIn scrape.")
                return []
            return self.search_jobs(
                role            = query["role"],
                location        = query["location"],
                keywords        = query.get("keywords", []),
                easy_apply_only = query.get("easy_apply_only", True),
                max_pages       = query.get("max_pages", 3),
                max_days_old    = query.get("max_days_old", 30),
                max_jobs        = query.get("max_jobs", 10),
                enrich_details  = query.get("enrich_details", False),
            )
        except ScraperError:
            raise
        except Exception as e:
            raise ScraperError(
                stage="scrape",
                code="linkedin_scrape_failed",
                message=str(e),
                retriable=True,
                details={"query": query, "run_id": self.run_id},
            ) from e
        finally:
            self.stop()




























