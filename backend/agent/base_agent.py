"""
base_agent.py
-------------
Abstract base class for all agents in the Job Application system.
Provides:
  - Cloudflare Workers AI LLM calls
  - Shared logger with redaction and run/job trace context
  - Common utility methods
"""

import json
import logging
import re
import time
from abc import ABC, abstractmethod
from typing import Any

import requests

import config
from agent.run_config import RunConfig


SENSITIVE_PATTERNS = [
    (re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]+"), r"\1***"),
    (re.compile(r"(?i)(api[_-]?token[\"'=:\s]+)[^\s,]+"), r"\1***"),
    (re.compile(r"(?i)(password[\"'=:\s]+)[^\s,]+"), r"\1***"),
    (re.compile(r"\b[\w\.-]+@[\w\.-]+\.\w+\b"), "***@***"),
    (re.compile(r"\b(?:\+?\d[\s\-()]*){8,}\b"), "***PHONE***"),
]


class _ContextAndRedactionFilter(logging.Filter):
    """Inject context defaults and redact common sensitive values."""

    def __init__(self, run_id: str):
        super().__init__()
        self.run_id = run_id

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "run_id"):
            record.run_id = self.run_id
        if not hasattr(record, "job_id"):
            record.job_id = "-"

        msg = record.getMessage()
        redacted = msg
        for pattern, replacement in SENSITIVE_PATTERNS:
            redacted = pattern.sub(replacement, redacted)

        if redacted != msg:
            record.msg = redacted
            record.args = ()
        return True


def _setup_logger(name: str, run_id: str = "-") -> logging.LoggerAdapter:
    """Create a logger that writes to file and stdout."""
    base_logger = logging.getLogger(name)
    if not base_logger.handlers:
        base_logger.setLevel(logging.DEBUG)
        fmt = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s "
            "[run_id=%(run_id)s job_id=%(job_id)s] %(message)s"
        )

        # File handler
        config.LOG_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(config.LOG_FILE_PATH, encoding="utf-8")
        fh.setFormatter(fmt)
        base_logger.addHandler(fh)

        # Console handler
        ch = logging.StreamHandler()
        ch.setFormatter(fmt)
        base_logger.addHandler(ch)

    has_filter = any(
        isinstance(existing, _ContextAndRedactionFilter)
        for existing in base_logger.filters
    )
    if not has_filter:
        base_logger.addFilter(_ContextAndRedactionFilter(run_id=run_id))

    return logging.LoggerAdapter(base_logger, {"run_id": run_id, "job_id": "-"})


class BaseAgent(ABC):
    """
    Abstract base class. Subclass this to create a new agent.

    Each agent has:
      - self.log     : a logger for that agent
      - self.ask_llm : sends a prompt to Cloudflare Workers AI

    Subclasses must implement the `run()` method.
    """

    def __init__(self, name: str, run_config: RunConfig | None = None):
        self.name = name
        self.run_config = run_config
        self.run_id = run_config.run_id if run_config else "-"
        self.log = _setup_logger(name, run_id=self.run_id)
        self.log.info(f"{self.name} initialised.")

    # ------------------------------------------------------------------
    # LLM interface - Cloudflare Workers AI
    # ------------------------------------------------------------------
    def ask_llm(
        self,
        prompt: str,
        system: str = "You are a helpful AI assistant.",
        temperature: float = 0.3,
        max_tokens: int = 1024,
    ) -> str:
        """
        Send a prompt to the Cloudflare Workers AI REST API and return
        the text response.

        Args:
            prompt      : The user message / task description.
            system      : The system prompt to set the agent's persona.
            temperature : Sampling temperature (0 = deterministic).
            max_tokens  : Maximum tokens in the LLM response.

        Returns:
            The LLM's text reply as a plain string.
        """
        if not config.CF_API_TOKEN or not config.CF_ACCOUNT_ID:
            raise RuntimeError(
                "Cloudflare credentials not set! "
                "Please fill CF_ACCOUNT_ID and CF_API_TOKEN in .env"
            )

        headers = {
            "Authorization": f"Bearer {config.CF_API_TOKEN}",
            "Content-Type": "application/json",
        }
        payload = {
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        self.log.debug(f"Calling Cloudflare AI | model={config.CF_MODEL}")

        max_retries = 3
        backoff_base = 5

        for attempt in range(max_retries):
            try:
                response = requests.post(
                    config.CF_API_URL,
                    headers=headers,
                    json=payload,
                    timeout=60,
                )

                if response.status_code in [429, 500, 502, 503, 504]:
                    wait = backoff_base * (attempt + 1)
                    self.log.warning(
                        f"Error {response.status_code}. Retrying in {wait}s... "
                        f"(Attempt {attempt + 1}/{max_retries})"
                    )
                    time.sleep(wait)
                    continue

                response.raise_for_status()
                data = response.json()

                result_text = data.get("result", {}).get("response", "")
                self.log.debug(
                    f"LLM response ({len(result_text)} chars): {result_text[:120]}..."
                )
                return result_text

            except requests.exceptions.HTTPError as e:
                self.log.error(f"HTTP error from Cloudflare AI: {e} - {response.text}")
                raise
            except Exception as e:
                self.log.error(f"Unexpected error calling LLM: {e}")
                raise

        raise RuntimeError("Cloudflare AI request failed after multiple retries due to rate limiting.")

    def ask_llm_json(
        self,
        prompt: str,
        system: str = "You are a helpful AI assistant. Always respond with valid JSON only.",
        **kwargs,
    ) -> dict:
        """
        Like ask_llm but expects JSON output.
        Robustly extracts the first valid JSON object from noisy model responses.
        Returns {} on parse failure.
        """
        raw = self.ask_llm(prompt, system=system, **kwargs).strip()

        # Strip fenced code blocks if present.
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
            raw = re.sub(r"\s*```$", "", raw).strip()

        # Fast path: direct JSON.
        try:
            return json.loads(raw)
        except Exception:
            pass

        # Try each balanced {...} candidate and return the first parsable object.
        starts = [i for i, ch in enumerate(raw) if ch == "{"]
        for start in starts:
            depth = 0
            for idx in range(start, len(raw)):
                ch = raw[idx]
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        candidate = raw[start : idx + 1]
                        try:
                            parsed = json.loads(candidate)
                            if isinstance(parsed, dict):
                                return parsed
                        except Exception:
                            break

        self.log.warning(f"JSON parse failed. Raw response:\n{raw[:500]}")
        return {}
    # ------------------------------------------------------------------
    # Shared utilities
    # ------------------------------------------------------------------
    def human_pause(self, multiplier: float = 1.0) -> None:
        """Sleep for HUMAN_DELAY_MS * multiplier milliseconds to mimic human pacing."""
        delay = (config.HUMAN_DELAY_MS * multiplier) / 1000
        time.sleep(delay)

    def log_action(self, action: str, detail: str = "") -> None:
        msg = f"ACTION: {action}"
        if detail:
            msg += f" | {detail}"
        self.log.info(msg)

    def log_for_job(self, level: str, job_id: str, message: str, **kwargs: Any) -> None:
        """Emit a log line with explicit job_id context."""
        logger_fn = getattr(self.log, level.lower(), self.log.info)
        logger_fn(message, extra={"job_id": job_id, **kwargs})

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------
    @abstractmethod
    def run(self, *args, **kwargs):
        """Each agent must implement its main execution method."""
        raise NotImplementedError

