"""Selector constants used by submission flow logic."""

EASY_APPLY_ACTION_SELECTORS = [
    ("submit", "button:has-text('Submit application')"),
    ("submit", "button[aria-label*='Submit application']"),
    ("submit", "button:has-text('Send application')"),
    ("submit", "button:has-text('Apply now')"),
    ("submit", "button[aria-label*='Send application']"),
    ("review", "button:has-text('Review')"),
    ("review", "button:has-text('Review application')"),
    ("next", "button[data-easy-apply-next-button]"),
    ("next", "button:has-text('Next')"),
    ("next", "button:has-text('Continue')"),
    ("next", "button:has-text('Continue to next step')"),
    ("next", "footer button.artdeco-button--primary"),
    ("next", "button.artdeco-button--primary"),
]

EXTERNAL_ACTION_SELECTORS = [
    ("submit", "button:has-text('Submit')"),
    ("submit", "input[type='submit']"),
    ("submit", "button:has-text('Submit application')"),
    ("submit", "button:has-text('Apply')"),
    ("submit", "a:has-text('Apply')"),
    ("submit", "button:has-text('Finish')"),
    ("submit", "button:has-text('Complete application')"),
    ("submit", "button:has-text('Send')"),
    ("review", "button:has-text('Review')"),
    ("next", "button:has-text('Next')"),
    ("next", "button:has-text('Continue')"),
    ("next", "button:has-text('Save and continue')"),
    ("next", "button:has-text('Continue to next step')"),
    ("next", "button:has-text('Proceed')"),
]

APPLY_BUTTON_SELECTORS = {
    "easy": [
        "button:has-text('Easy Apply')",
        "button[aria-label*='Easy Apply']",
        ".jobs-apply-button:has-text('Easy Apply')",
    ],
    "external": [
        "button:has-text('Apply')",
        "a:has-text('Apply')",
        ".jobs-apply-button",
    ],
}

SUBMISSION_CONFIRMATION_SELECTORS = [
    ".artdeco-inline-feedback--success",
    "h2:has-text('Application submitted')",
    "h2:has-text('application was sent')",
    "span:has-text('Application submitted')",
    "[data-test-modal]:has-text('submitted')",
    ".jobs-s-apply--posted",
    "text='Thank you for applying'",
    "text='Application received'",
    "text='Your application has been submitted'",
]

APPLIED_STATE_SELECTORS = [
    "button[aria-label*='Applied']",
    "span.jobs-apply-button--top-card:has-text('Applied')",
    "div.jobs-apply-button--top-card:has-text('Applied')",
    ".jobs-s-apply--posted",
    "button:has-text('Applied')",
]

VALIDATION_ERROR_SELECTORS = [
    ".artdeco-inline-feedback__message",
    ".artdeco-inline-feedback--error",
    ".fb-dash-form-element__error-message",
    "[role='alert']",
    ".jobs-easy-apply-form-section__grouping .t-12.t-normal",
    "text='Please enter a valid answer'",
    "text='This field is required'",
    "text='Enter a valid'",
]

