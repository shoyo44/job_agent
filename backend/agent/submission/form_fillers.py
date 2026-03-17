"""Reusable form field extraction helpers for submission automation."""

import re

from playwright.sync_api import Locator


def normalise_attrs(locator: Locator) -> str:
    """Collect common identifying attributes for a form element."""
    return " ".join([
        (locator.get_attribute("id") or ""),
        (locator.get_attribute("name") or ""),
        (locator.get_attribute("placeholder") or ""),
        (locator.get_attribute("aria-label") or ""),
    ]).lower()


def extract_question_text(locator: Locator) -> str:
    """Infer visible question text associated with a form control."""
    snippets = []
    try:
        attrs = normalise_attrs(locator)
        if attrs:
            snippets.append(attrs)
    except Exception:
        pass

    xpath_candidates = [
        "ancestor::label[1]",
        "ancestor::*[self::div or self::fieldset][1]//label[1]",
        "ancestor::*[self::div or self::fieldset][1]//legend[1]",
        "ancestor::*[self::div or self::fieldset][1]//*[contains(@class,'label')][1]",
        "ancestor::*[self::div or self::fieldset][1]//*[contains(@class,'question')][1]",
    ]
    for xpath in xpath_candidates:
        try:
            node = locator.locator(f"xpath={xpath}").first
            if node.count() > 0:
                text = (node.text_content() or "").strip()
                if text:
                    snippets.append(text)
        except Exception:
            continue

    joined = " | ".join(part for part in snippets if part)
    return re.sub(r"\s+", " ", joined).strip()

