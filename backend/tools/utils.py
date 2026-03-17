"""
utils.py
--------
General shared utilities used across the project.
"""

import random
import time
import logging

log = logging.getLogger("utils")


def random_delay(min_ms: int = 800, max_ms: int = 2500) -> None:
    """
    Sleeps for a random duration between min_ms and max_ms milliseconds.
    Used to mimic human-like behaviour during scraping and form filling
    to avoid triggering bot detection.
    """
    delay = random.randint(min_ms, max_ms) / 1000
    time.sleep(delay)


def truncate(text: str, max_len: int = 100) -> str:
    """Returns a truncated version of text with '...' if it's too long."""
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."


def flatten_list(nested: list) -> list:
    """Flattens one level of nesting in a list of lists."""
    return [item for sublist in nested for item in sublist]


def deduplicate_jobs(jobs: list, seen_ids: set) -> list:
    """
    Removes duplicate JobListing objects based on job_id.
    Updates seen_ids in-place.
    """
    unique = []
    for job in jobs:
        if job.job_id not in seen_ids:
            unique.append(job)
            seen_ids.add(job.job_id)
    return unique


def safe_get(d: dict, *keys, default=None):
    """
    Safely navigates nested dicts.
    Example: safe_get(data, "result", "response", default="")
    """
    current = d
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key, default)
        if current is None:
            return default
    return current


def format_table(headers: list[str], rows: list[list]) -> str:
    """
    Simple ASCII table formatter for terminal output.
    Example:
        headers = ["Title", "Company", "Score"]
        rows = [["AI Engineer", "OpenAI", "92"]]
    """
    col_widths = [max(len(str(h)), max((len(str(r[i])) for r in rows), default=0))
                  for i, h in enumerate(headers)]

    sep = "+" + "+".join("-" * (w + 2) for w in col_widths) + "+"
    fmt = "|" + "|".join(f" {{:<{w}}} " for w in col_widths) + "|"

    lines = [sep, fmt.format(*headers), sep]
    for row in rows:
        lines.append(fmt.format(*[str(v) for v in row]))
    lines.append(sep)
    return "\n".join(lines)
