"""Shared flow control helper for multi-step form submission."""

from playwright.sync_api import Locator, Page

from agent.planner_agent import JobListing


def attempt_action_with_repair(
    *,
    agent,
    action_button: Locator,
    action_type: str,
    page: Page,
    form_scope: Locator,
    job: JobListing,
    resume_summary: str,
    cover_letter: str,
) -> tuple[bool, list[str]]:
    """
    Click an action button and retry once after repair if validation errors appear.

    `agent` is SubmissionAgent-like and must expose:
      - human_pause
      - _collect_visible_errors
      - _repair_invalid_fields
    """
    # Final pre-click radio sweep for required yes/no groups.
    try:
        if hasattr(agent, "_force_answer_required_radios"):
            agent._force_answer_required_radios(form_scope, resume_summary, cover_letter)
    except Exception:
        pass

    if hasattr(agent, "_safe_click"):
        clicked = agent._safe_click(action_button, f"{action_type} action button")
        if not clicked:
            return False, ["Could not click action button"]
    else:
        action_button.click()
    agent.human_pause(1.2)

    errors = agent._collect_visible_errors(form_scope)
    if not errors:
        return True, []

    agent.log.warning(
        f"{job.title}: validation errors after {action_type}: {' | '.join(errors[:3])}"
    )
    agent._repair_invalid_fields(form_scope, resume_summary, cover_letter)

    try:
        if hasattr(agent, "_force_answer_required_radios"):
            agent._force_answer_required_radios(form_scope, resume_summary, cover_letter)
    except Exception:
        pass

    agent.human_pause(0.8)

    retry_button = None
    if action_type == "submit":
        retry_button = form_scope.locator(
            "button:has-text('Submit application'), "
            "button[aria-label*='Submit application']"
        ).first
    elif action_type == "review":
        retry_button = form_scope.locator("button:has-text('Review')").first
    else:
        retry_button = form_scope.locator(
            "button[data-easy-apply-next-button], "
            "button:has-text('Next'), "
            "button:has-text('Continue')"
        ).first

    try:
        if retry_button and retry_button.count() > 0 and retry_button.is_visible():
            if hasattr(agent, "_safe_click"):
                agent._safe_click(retry_button, f"retry {action_type} action button")
            else:
                retry_button.click()
            agent.human_pause(1.2)
    except Exception:
        pass

    return len(agent._collect_visible_errors(form_scope)) == 0, errors
