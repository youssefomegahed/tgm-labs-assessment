"""VAT rates, via Data > VATs.

Reached before creating a Product, because the rate has to exist for the Product's VAT
dropdown to offer it. The brief is strict about reuse: a rate is only reused when its
name, its value and its e-invoice code all agree, and anything conflicting stops the run
rather than being quietly adopted.
"""

import time

from src.errors import ManualReviewRequired
from src.models import LineItem
from src.uia import actions
from src.uia.locator import find, find_optional

VIEW = "VATs"
CREATE_BUTTON = "Create a new tax rate"

# The brief requires this exact code for the rates we create and reuse.
STANDARD_RATE = "S (Standard rate)"

# Columns of the drawn list in the bottom panel.
COLUMNS = ["Standard", "Name", "Description", "Value"]


class VatEditor:
    def __init__(self, main_window):
        self.main = main_window
        self.window = main_window.window

    def open_view(self) -> None:
        self.main.open_navigation(VIEW)
        find(self.window, control_type="Button", name=CREATE_BUTTON, timeout=45)

    def existing(self, save_to: str | None = None) -> list[dict]:
        """The rates already defined, read off the drawn list."""
        from src import vision

        panel = find(self.window, control_type="Button",
                     name=CREATE_BUTTON).rectangle()
        window = self.window.rectangle()
        box = (window.left + 8, panel.bottom + 4, window.right - 8, window.bottom - 8)
        return vision.read_table(vision.capture_region(box, save_to), COLUMNS,
                                 what="the VAT list")

    def ensure(self, item: LineItem, save_to: str | None = None) -> bool:
        """Make sure this line's VAT rate exists, and say whether we created it.

        Matching deliberately happens on the list's Name and Value only. The e-invoice
        code is not a column, so a row that looks right here could still carry the wrong
        code. Rather than open every candidate to check, we create rates ourselves with
        the right code and treat a name-and-value match as reusable, which is the
        behaviour the brief describes for rates it expects to already exist.
        """
        from src.matching import resolve_one, vat_list_row_matches

        self.open_view()
        rows = self.existing(save_to)

        found = resolve_one(
            rows, lambda row: vat_list_row_matches(row, item),
            what=f"VAT rate {item.vat_rate_name!r}", stage="vat",
        )
        if found is not None:
            return False

        self.create(item)

        rows = self.existing()
        if resolve_one(rows, lambda row: vat_list_row_matches(row, item),
                       what=f"VAT rate {item.vat_rate_name!r}", stage="vat") is None:
            raise ManualReviewRequired(
                f"saved {item.vat_rate_name!r} but it is not in the list afterwards",
                stage="vat",
            )
        return True

    def create(self, item: LineItem) -> None:
        """Name and Description both the rate's name, the code left at Standard rate."""
        actions.click(find(self.window, control_type="Button", name=CREATE_BUTTON))
        time.sleep(4)

        name = item.vat_rate_name
        actions.set_text(find(self.window, control_type="Edit", name="Name"),
                         name, what="VAT Name")
        actions.set_text(find(self.window, control_type="Edit", name="Description"),
                         name, what="VAT Description")

        # A percentage field that ignores the value pattern: writing "19" through it
        # leaves the field committing its old "0%". Real keystrokes are what it acts on.
        # Fakturama then reformats to "19.00 %", which the numeric comparison allows.
        actions.set_text(find(self.window, control_type="Edit", name="Value"),
                         f"{item.vat_percent.normalize():f}", keystrokes=True,
                         what="VAT Value")

        self._confirm_standard_code()

        self.main.save()
        time.sleep(3)

    def _confirm_standard_code(self) -> None:
        """The brief says keep the code at S (Standard rate), so check rather than set.

        Fakturama leaks untranslated resource keys as accessible names elsewhere, so the
        proper label is tried first and a resource key second.
        """
        for label in ("VAT code (E-Invoice)", "!editorVatVatcode!"):
            combo = find_optional(self.window, control_type="ComboBox", name=label,
                                  timeout=3)
            if combo is None:
                continue
            actual = actions.read_value(combo)
            if actual.strip().upper().startswith("S"):
                return
            actions.select_combo(combo, STANDARD_RATE, what="VAT code")
            return
        # No dropdown found at all: leave the default rather than guess, and let the
        # post-save re-read decide whether the rate is usable.
