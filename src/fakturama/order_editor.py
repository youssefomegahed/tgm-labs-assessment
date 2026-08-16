"""The New Order editor.

Exposes intent. Nothing above this file knows that Cust.Ref. happens to be a named Edit
while Date is an anonymous one sitting to the right of its label.

The header, addresses, VAT mode and totals are the same controls the Invoice editor
carries, so they live on `DocumentEditor`. What is genuinely an Order's own is here: the
price mode, the two selector icons the brief warns about, and the follow-up buttons.
"""

import time
from datetime import date

from src.errors import VerificationFailed
from src.fakturama.document_editor import DocumentEditor, format_date
from src.uia import actions
from src.uia.locator import find, labelled, stacked_icons

__all__ = ["OrderEditor", "format_date"]


class OrderEditor(DocumentEditor):
    TAB = "New Order"

    # --- reading -------------------------------------------------------------

    @property
    def order_date(self) -> str:
        return actions.read_value(labelled(self.window, "Date"))

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

    def create_follow_up(self, kind: str = "Invoice") -> None:
        """Click a button in the Create a follow-up document group.

        The brief is emphatic that the Invoice must be made this way rather than from
        the top toolbar, because only the follow-up action keeps the Order relationship.
        The group is found by name first so a same-named toolbar button cannot be hit by
        accident.
        """
        group = find(self.window, control_type="Group",
                     name="Create a follow-up document")
        actions.click(find(group, control_type="Button", name=kind))
        actions.park_pointer()

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
