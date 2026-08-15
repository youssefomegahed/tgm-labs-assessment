"""Creating a payment method, via Data > terms of payment.

Only reached when the Debtor's Payment dropdown does not already offer the method the
document names. The Debtor editor stays open behind this the whole time.
"""

import time

from src.errors import ManualReviewRequired
from src.uia import actions
from src.uia.locator import find, find_optional, labelled

VIEW = "terms of payment"
CREATE_BUTTON = "Create a new term of payment"

# The brief's mapping from what a document says to what Fakturama calls it.
PAYMENT_CODES = {
    "Bank Transfer": "Credit transfer",
    "Credit Card": "Credit card",
    "SEPA Direct Debit": "SEPA direct debit",
}

# Fakturama leaks an untranslated resource key as this dropdown's accessible name. It
# works as a locator, but it is exactly the kind of thing that changes when somebody
# fixes the translation, so the proper label is tried first.
PAYMENT_CODE_LABELS = ("Payment code", "!editorPaymentPaymentcode!")

# Columns of the list in the bottom panel, which is drawn and so has to be read visually.
COLUMNS = ["Standard", "Name", "Description", "Discount", "Disc. Days", "Net Days"]


class PaymentEditor:
    def __init__(self, main_window):
        self.main = main_window
        self.window = main_window.window

    def open_view(self) -> None:
        self.main.open_navigation(VIEW)
        # The view builds in the bottom panel and is slow to appear under emulation.
        find(self.window, control_type="Button", name=CREATE_BUTTON, timeout=45)

    def existing(self, save_to: str | None = None) -> list[dict]:
        """The methods already defined, read off the drawn list."""
        from src import vision

        create = find(self.window, control_type="Button", name=CREATE_BUTTON)
        panel = create.rectangle()
        window = self.window.rectangle()
        box = (window.left + 8, panel.bottom + 4, window.right - 8, window.bottom - 8)
        return vision.read_table(
            vision.capture_region(box, save_to), COLUMNS, what="terms of payment"
        )

    def create(self, method: str) -> None:
        """Fill in a new payment method exactly as the brief specifies.

        Name and Description both take the method's name, Account is left blank, the
        three day counts are zeroed, the three message texts are left blank, and Set as
        standard is deliberately not touched.
        """
        code = PAYMENT_CODES.get(method)
        if code is None:
            raise ManualReviewRequired(
                f"no payment code mapping for {method!r}; the brief covers "
                f"{', '.join(sorted(PAYMENT_CODES))}",
                stage="payment method",
            )

        actions.click(find(self.window, control_type="Button", name=CREATE_BUTTON))
        time.sleep(4)

        actions.set_text(find(self.window, control_type="Edit", name="Name"),
                         method, what="payment Name")
        actions.set_text(find(self.window, control_type="Edit", name="Description"),
                         method, what="payment Description")

        actions.select_combo(self._payment_code_combo(), code, what="payment code")

        for field in ("Cash discount", "Discount Days", "Net Days"):
            actions.set_text(find(self.window, control_type="Edit", name=field),
                             "0", what=field)

        self.main.save()
        time.sleep(3)

    # --- internals -----------------------------------------------------------

    def _payment_code_combo(self):
        for label in PAYMENT_CODE_LABELS:
            combo = find_optional(self.window, control_type="ComboBox", name=label,
                                  timeout=3)
            if combo is not None:
                return combo

        # Neither name matched, so fall back to position: the dropdown directly below
        # Description, which is stable even when the label is not.
        return labelled(self.window, "Description", control_type="ComboBox")
