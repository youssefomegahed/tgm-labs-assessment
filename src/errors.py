"""Failure modes the flow can hit.

The brief says "stop for manual review" in six different places: an ambiguous Debtor
match, a conflicting VAT definition, a Product that is still missing after we saved it,
a Payment Method the Invoice will not offer, and so on. Rather than scatter that
decision through the flow, every one of them raises the same exception, which run.py
catches once and writes to the run log with whatever screenshot was current.
"""


class AutomationError(Exception):
    """Base for anything this project raises on purpose."""


class ManualReviewRequired(AutomationError):
    """The flow found something it is not allowed to guess about, and stopped.

    This is a deliberate halt, not a crash. The reason is written for a human who has
    to open Fakturama and decide.
    """

    def __init__(self, reason: str, *, stage: str = "", screenshot: str | None = None):
        self.reason = reason
        self.stage = stage
        self.screenshot = screenshot
        super().__init__(f"[{stage}] {reason}" if stage else reason)


class ExtractionError(AutomationError):
    """The source image did not yield usable data."""


class ControlNotFound(AutomationError):
    """A UI control could not be grounded by any available strategy."""


class VerificationFailed(AutomationError):
    """We set a value, read it back, and got something else."""

    def __init__(self, what: str, expected: object, actual: object):
        self.what = what
        self.expected = expected
        self.actual = actual
        super().__init__(f"{what}: expected {expected!r}, read back {actual!r}")
