"""
errors.py
---------
Structured error types used across scraping and submission flows.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentError(Exception):
    """Base structured error for pipeline stages."""

    stage: str
    code: str
    message: str
    retriable: bool = False
    details: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return f"{self.stage}:{self.code}: {self.message}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "code": self.code,
            "message": self.message,
            "retriable": self.retriable,
            "details": self.details,
        }


class ScraperError(AgentError):
    """Errors raised by web scrapers."""


class SubmissionError(AgentError):
    """Errors raised during application submission."""
