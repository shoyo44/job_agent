"""Result and validation detection helpers for submission flow."""

from playwright.sync_api import Locator, Page

from agent.submission.selectors import (
    APPLIED_STATE_SELECTORS,
    SUBMISSION_CONFIRMATION_SELECTORS,
    VALIDATION_ERROR_SELECTORS,
)


def is_submission_confirmed(page: Page) -> bool:
    """Detect common post-submit confirmation text and applied badges."""
    for selector in SUBMISSION_CONFIRMATION_SELECTORS:
        try:
            node = page.locator(selector).first
            if node.count() > 0 and node.is_visible():
                return True
        except Exception:
            continue

    for selector in APPLIED_STATE_SELECTORS:
        try:
            node = page.locator(selector).first
            if node.count() > 0 and node.is_visible():
                return True
        except Exception:
            continue

    return False


def collect_visible_errors(page: Locator | Page) -> list[str]:
    """Collect visible validation and inline error messages from the current form."""
    messages: list[str] = []
    seen: set[str] = set()
    for selector in VALIDATION_ERROR_SELECTORS:
        try:
            for node in page.locator(selector).locator("visible=true").all():
                text = (node.text_content() or "").strip()
                if text and text not in seen:
                    seen.add(text)
                    messages.append(text)
        except Exception:
            continue
    return messages

