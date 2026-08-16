"""The New Order editor.

Exposes intent. Nothing above this file knows that Cust.Ref. happens to be a named Edit
while Date is an anonymous one sitting to the right of its label.
"""

import time
from datetime import date

from src.errors import VerificationFailed
from src.uia import actions
from src.uia.locator import find, labelled, stacked_icons

# Fakturama renders dates as "Aug 15, 2026" in the running locale. strftime's %d pads to
# two digits and the widget does not, so the day is formatted by hand.
def format_date(value: date) -> str:
    return f"{value:%b} {value.day}, {value.year}"


class OrderEditor:
    """Wraps the whole application window, since the editor is a tab inside it."""

    TAB = "New Order"

    def __init__(self, main_window):
        self.main = main_window
        self.window = main_window.window

    # --- reading -------------------------------------------------------------

    @property
    def document_number(self) -> str:
        """The proposed No., which the brief says to leave alone. Read to log it."""
        return actions.read_value(labelled(self.window, "No."))

    @property
    def customer_reference(self) -> str:
        return actions.read_value(find(self.window, control_type="Edit", name="Cust.Ref."))

    @property
    def order_date(self) -> str:
        return actions.read_value(labelled(self.window, "Date"))

    def address_block(self, which: str = "Invoice address") -> str:
        """The address text the Order shows for the selected Debtor.

        This is what the brief means by confirming the populated Invoice address, and it
        is the authoritative check after a selection: it comes from the saved record
        rather than from a grid cell, which may be clipped or showing a different one of
        the debtor's addresses.

        Found through the address tab that contains it rather than from the "Addresses"
        label, because the block sits below that label rather than beside it.
        """
        from src.uia.locator import find_all

        container = find(self.window, control_type="Tab", name=which)
        blocks = find_all(container, control_type="Edit")
        if not blocks:
            raise LookupError(f"no address block inside the {which!r} tab")

        # The block is the tall multi-line box, not any small field sharing the tab.
        biggest = max(blocks, key=lambda edit: edit.rectangle().height())
        return actions.read_value(biggest)

    def totals(self) -> dict[str, str]:
        """What the editor currently believes the document comes to.

        The first row is labelled "Total Net" or "Total Gross" depending on the price
        mode, so it is looked up by either name rather than assumed.
        """
        from src.uia.locator import find_optional

        found = {}
        for label in ("Total Net", "Total Gross", "Discount", "VAT", "Total"):
            element = find_optional(
                self.window, control_type="Edit", name=label, timeout=2
            )
            if element is not None:
                found[label.lower().replace(" ", "_")] = actions.read_value(element)
        return found

    # --- writing -------------------------------------------------------------

    def set_date(self, value: date) -> None:
        """Set the Date and confirm it after the field has lost focus.

        The date box is a parsed field, not a plain text box. Writing to it and reading
        straight back shows the new text, because the text really is sitting there, but
        the widget re-parses on focus loss and reverts to its previous value if it did
        not like what it got. Verifying before the field commits is verifying nothing.

        So: type real keystrokes, move focus away with Tab, and only then read back.
        """
        wanted = format_date(value)
        # Digits only, in the order the field displays: month, day, year. Typing the
        # formatted string scatters across the segments: "Jul 14, 2026" came back as
        # "Aug 20, 0026", the letters having nudged the month and the digits landing
        # wherever the caret happened to be. Each segment takes its digits and the
        # caret advances on its own, so no separators are needed.
        digits = f"{value.month:02d}{value.day:02d}{value.year:04d}"

        for _ in range(3):
            field = labelled(self.window, "Date")
            field.set_focus()
            # Home puts the caret on the first segment whatever it was showing before.
            field.type_keys("{HOME}", pause=0.05)
            field.type_keys(digits, pause=0.12)
            field.type_keys("{TAB}")
            time.sleep(0.8)

            if actions.read_value(labelled(self.window, "Date")) == wanted:
                return

        raise VerificationFailed("Date", wanted,
                                 actions.read_value(labelled(self.window, "Date")))

    def set_customer_reference(self, value: str) -> None:
        actions.set_text(
            find(self.window, control_type="Edit", name="Cust.Ref."),
            value,
            what="Cust.Ref.",
        )

    def set_price_mode(self, mode: str = "Net") -> None:
        """Net or Gross, the unnamed dropdown on the header row.

        It has no name and no label of its own, so it is found as the one ComboBox on
        the same row as the Date field.
        """
        actions.select_combo(self._price_mode_combo(), mode, what="price mode")

    def confirm_vat_mode(self, expected: str = "With VAT") -> str:
        combo = find(self.window, control_type="ComboBox", name="VAT")
        actual = actions.read_value(combo)
        if actual != expected:
            actions.select_combo(combo, expected, what="VAT mode")
        return expected

    # --- the two icons the brief warns about ---------------------------------

    def open_address_selector(self) -> None:
        """The upper icon beside Addresses, which picks an existing Debtor.

        The lower one starts a new Debtor and would take the flow down the wrong
        branch, which is exactly the mistake the brief calls out.
        """
        icons = stacked_icons(self.window, "Addresses")
        if len(icons) < 2:
            raise LookupError(
                f"expected two icons beside Addresses, found {len(icons)}"
            )
        icons[0].click_input()

    def open_product_selector(self) -> None:
        """The upper icon beside Items, not the green plus below it."""
        icons = stacked_icons(self.window, "Items")
        if not icons:
            raise LookupError("no icons found beside Items")
        icons[0].click_input()

    # --- internals -----------------------------------------------------------

    def _price_mode_combo(self):
        from src.uia.locator import iter_descendants

        row = labelled(self.window, "Date").rectangle()
        middle = (row.top + row.bottom) / 2

        for element in iter_descendants(self.window):
            if element.element_info.control_type != "ComboBox":
                continue
            rect = element.rectangle()
            if rect.top <= middle <= rect.bottom and rect.left > row.right:
                return element

        raise LookupError("no price mode dropdown on the Date row")
