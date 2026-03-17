"""
config.py
---------
Central configuration loader. All modules should import from here
rather than reading environment variables directly.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from the project root
load_dotenv(Path(__file__).parent / ".env")

# ------------------------------------------------------------------
# Cloudflare Workers AI
# ------------------------------------------------------------------
CF_ACCOUNT_ID: str = os.getenv("CF_ACCOUNT_ID", "")
CF_API_TOKEN: str = os.getenv("CF_API_TOKEN", "")
CF_MODEL: str = os.getenv("CF_MODEL", "@cf/meta/llama-3.1-8b-instruct")
CF_API_URL: str = (
    f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}"
    f"/ai/run/{CF_MODEL}"
)

# ------------------------------------------------------------------
# Job Site Credentials
# ------------------------------------------------------------------
LINKEDIN_EMAIL: str = os.getenv("LINKEDIN_EMAIL", "")
LINKEDIN_PASSWORD: str = os.getenv("LINKEDIN_PASSWORD", "")

# ------------------------------------------------------------------
# User Profile
# ------------------------------------------------------------------
USER_NAME: str = os.getenv("USER_NAME", "")
USER_EMAIL: str = os.getenv("USER_EMAIL", os.getenv("LINKEDIN_EMAIL", ""))
USER_PHONE: str = os.getenv("USER_PHONE", "")
USER_LOCATION: str = os.getenv("USER_LOCATION", "Bangalore")
USER_RESUME_PATH: Path = Path(os.getenv("USER_RESUME_PATH", "data/resume.pdf"))
USER_TARGET_ROLES: list[str] = [
    r.strip() for r in os.getenv("USER_TARGET_ROLES", "").split(",") if r.strip()
]
USER_TARGET_LOCATIONS: list[str] = [
    l.strip() for l in os.getenv("USER_TARGET_LOCATIONS", "").split(",") if l.strip()
]
USER_MIN_SALARY: int = int(os.getenv("USER_MIN_SALARY", "0"))
USER_WORK_MODE: str = os.getenv("USER_WORK_MODE", "any")  # remote/onsite/hybrid/any

# Extended profile — used for LinkedIn Easy Apply form fields
USER_YEARS_EXPERIENCE: str = os.getenv("USER_YEARS_EXPERIENCE", "2")
USER_LINKEDIN_URL: str = os.getenv("USER_LINKEDIN_URL", "")
USER_PORTFOLIO_URL: str = os.getenv("USER_PORTFOLIO_URL", "")
# Work authorisation for the target country (yes/no)
USER_WORK_AUTHORIZED: str = os.getenv("USER_WORK_AUTHORIZED", "yes")
# Requires visa sponsorship (yes/no)
USER_REQUIRES_SPONSORSHIP: str = os.getenv("USER_REQUIRES_SPONSORSHIP", "no")

# ------------------------------------------------------------------
# Agent Settings
# ------------------------------------------------------------------
MIN_CONFIDENCE_SCORE: int = int(os.getenv("MIN_CONFIDENCE_SCORE", "65"))
MAX_APPLICATIONS_PER_RUN: int = int(os.getenv("MAX_APPLICATIONS_PER_RUN", "10"))
DRY_RUN: bool = os.getenv("DRY_RUN", "true").lower() == "true"

# ------------------------------------------------------------------
# Data / Tracking
# ------------------------------------------------------------------
EXCEL_FILE_PATH: Path = Path(os.getenv("EXCEL_FILE_PATH", "data/list.xlsx"))
LOG_FILE_PATH: Path = Path(os.getenv("LOG_FILE_PATH", "data/agent.log"))
MONGODB_URI: str = os.getenv("MONGODB_URI", "").strip()
MONGODB_DB: str = os.getenv("MONGODB_DB", "job_agent").strip()
MONGODB_COLLECTION: str = os.getenv("MONGODB_COLLECTION", "applications").strip()

# ------------------------------------------------------------------
# Browser / Scraping
# ------------------------------------------------------------------
# Path to a locally installed Chromium or Chrome binary.
# Empty string = use Playwright's own bundled Chromium (default).
CHROMIUM_PATH: str = os.getenv("CHROMIUM_PATH", "").strip()
HEADLESS: bool = os.getenv("HEADLESS", "false").lower() == "true"
HUMAN_DELAY_MS: int = int(os.getenv("HUMAN_DELAY_MS", "1500"))
# When true, use a fresh temporary browser profile each run (helps visibility/debugging).
USE_TEMP_BROWSER_PROFILE: bool = os.getenv("USE_TEMP_BROWSER_PROFILE", "false").lower() == "true"
