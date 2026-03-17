"""
job_tools.py
------------
Utility functions for parsing and normalising job listing data.
"""

import hashlib
import re
from datetime import datetime, timedelta
from urllib.parse import urlparse, urlunparse


def make_job_id(platform: str, company: str, title: str, url: str = "") -> str:
    """
    Creates a deterministic unique job ID from the platform, company, and title.
    Strips URL query params and fragments (e.g. LinkedIn's eBP/refId/trackingId)
    before hashing so the same job found via different searches gets the same ID.
    Uses a short MD5 hash to avoid very long strings.
    """
    if url:
        parsed = urlparse(url)
        clean_url = urlunparse(parsed._replace(query="", fragment=""))
    else:
        clean_url = ""
    raw = f"{platform}:{company.lower().strip()}:{title.lower().strip()}:{clean_url}"
    return hashlib.md5(raw.encode()).hexdigest()[:16]


def normalise_work_mode(text: str) -> str:
    """
    Extracts a normalised work mode from a raw job listing string.
    Returns one of: 'remote', 'onsite', 'hybrid', 'unknown'
    """
    text = text.lower()
    if "remote" in text:
        if "hybrid" in text or "onsite" in text or "office" in text:
            return "hybrid"
        return "remote"
    if "hybrid" in text:
        return "hybrid"
    if "onsite" in text or "on-site" in text or "in office" in text or "in-office" in text:
        return "onsite"
    return "unknown"


def normalise_salary(text: str) -> str:
    """
    Returns the raw salary string cleaned up.
    We don't parse it into numbers here — the LLM handles that.
    """
    if not text:
        return "Not specified"
    # Remove excessive whitespace
    return re.sub(r"\s+", " ", text.strip())


def parse_date_posted(text: str) -> str:
    """
    Converts relative date strings like "2 days ago", "Just posted" etc.
    to an ISO date string (YYYY-MM-DD).
    Falls back to today's date if it can't parse.
    """
    now = datetime.now()
    text = text.lower().strip()

    if "just" in text or "today" in text or "hour" in text or "minute" in text:
        return now.strftime("%Y-%m-%d")
    if "yesterday" in text:
        return (now - timedelta(days=1)).strftime("%Y-%m-%d")

    # "N days ago"
    match = re.search(r"(\d+)\s+day", text)
    if match:
        days = int(match.group(1))
        return (now - timedelta(days=days)).strftime("%Y-%m-%d")

    # "N weeks ago"
    match = re.search(r"(\d+)\s+week", text)
    if match:
        weeks = int(match.group(1))
        return (now - timedelta(weeks=weeks)).strftime("%Y-%m-%d")

    # "N months ago"
    match = re.search(r"(\d+)\s+month", text)
    if match:
        months = int(match.group(1))
        return (now - timedelta(days=30 * months)).strftime("%Y-%m-%d")

    # Return today as fallback
    return now.strftime("%Y-%m-%d")


def clean_description(text: str) -> str:
    """
    Strips HTML tags and excessive whitespace from a job description.
    """
    # Remove HTML tags
    text = re.sub(r"<[^>]+>", " ", text)
    # Remove multiple newlines
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Remove multiple spaces
    text = re.sub(r" {2,}", " ", text)
    return text.strip()


def is_too_old(date_str: str, max_days: int = 30) -> bool:
    """
    Returns True if the job was posted more than max_days ago.
    Used to filter out stale listings.
    """
    try:
        posted = datetime.strptime(date_str, "%Y-%m-%d")
        return (datetime.now() - posted).days > max_days
    except ValueError:
        return False
