"""What an Order editor and an Invoice editor have in common.

Fakturama builds both from the same form. The header carries a document number, a
Cust.Ref. and a VAT mode; the middle carries the addresses and the item grid; the bottom
right carries the totals. Only what surrounds that differs: an Order has a price mode
and the two selector icons, an Invoice has the paid row.

So the shared readers live here and the two editors add their own parts. This is a
smaller thing than the four parallel resolve-or-create implementations the design doc
argues for keeping separate: those differ in every column and every rule, while these
are the same controls with the same names on the same form.
"""

from datetime import date

from src.uia import actions
from src.uia.locator import find, find_optional, labelled


# Fakturama renders dates as "Aug 15, 2026" in the running locale. strftime's %d pads to
# two digits and the widget does not, so the day is formatted by hand.
def format_date(value: date) -> str:
    return f"{value:%b} {value.day}, {value.year}"


class DocumentEditor:
    """Wraps the whole application window, since an editor is a tab inside it."""

    TAB = ""

    def __init__(self, main_window):
        self.main = main_window
        self.window = main_window.window

    # --- reading -------------------------------------------------------------

    @property
    def document_number(self) -> str:
        """The proposed No., which the brief says to leave alone on both documents."""
        return actions.read_value(labelled(self.window, "No."))

    @property
    def customer_reference(self) -> str:
        return actions.read_value(
            find(self.window, control_type="Edit", name="Cust.Ref."))

    def has_address_tab(self, which: str) -> bool:
        """Is there an address tab of this name?

        Asked of the `TabItem`, which is the tab's handle in the strip, not of the `Tab`,
        which is its page. SWT does not realize a page until its tab is selected, so a
        document that plainly shows "Invoice address | Delivery address" has only one
        `Tab` in the tree. Asking the wrong one of the two reports a delivery address as
        missing on a document that has one.
        """
        return find_optional(self.window, control_type="TabItem", name=which,
                             timeout=3) is not None

    def address_block(self, which: str = "Invoice address") -> str:
        """The address text the document shows for the selected Debtor.

        This is the authoritative check after a selection: it comes from the saved
        record rather than from a grid cell, which may be clipped or showing a different
        one of the debtor's addresses.

        The tab is selected before it is read, for the realization reason above: the page
        of an unselected tab does not exist to be read.
        """
        from src.uia.locator import find_all

        item = find_optional(self.window, control_type="TabItem", name=which, timeout=5)
        if item is None:
            return ""
        try:
            actions.select_tab(item, what=which)
        except Exception:
            return ""

        container = find_optional(self.window, control_type="Tab", name=which,
                                  timeout=5)
        if container is None:
            return ""

        blocks = find_all(container, control_type="Edit")
        if not blocks:
            return ""

        # The block is the tall multi-line box, not any small field sharing the tab.
        biggest = max(blocks, key=lambda edit: edit.rectangle().height())
        return actions.read_value(biggest)

    def totals(self) -> dict[str, str]:
        """What the editor currently believes the document comes to.

        The first row is labelled "Total Net" or "Total Gross" depending on the price
        mode, so it is looked up by either name rather than assumed.
        """
        found = {}
        for label in ("Total Net", "Total Gross", "Discount", "VAT", "Total"):
            element = find_optional(
                self.window, control_type="Edit", name=label, timeout=2
            )
            if element is not None:
                found[label.lower().replace(" ", "_")] = actions.read_value(element)
        return found

    def net_total(self) -> str:
        """Whichever of Total Net / Total Gross this document is showing."""
        totals = self.totals()
        return totals.get("total_net") or totals.get("total_gross") or ""

    def shipping(self) -> tuple[str, str]:
        """The shipping method and what it costs, as (name, cost).

        The cost has no label of its own. It is the Edit to the right of the Shipping
        dropdown, on the same row, which is the same anchor-relative rule the rest of
        this form needs, taken rightwards instead of leftwards.
        """
        from src.uia.locator import iter_descendants

        combo = find_optional(self.window, control_type="ComboBox", name="Shipping",
                              timeout=5)
        if combo is None:
            return "", ""

        box = combo.rectangle()
        middle = (box.top + box.bottom) / 2

        to_the_right = []
        for element in iter_descendants(self.window):
            if element.element_info.control_type != "Edit":
                continue
            rect = element.rectangle()
            if rect.top <= middle <= rect.bottom and rect.left >= box.right - 4:
                to_the_right.append((rect.left, element))

        cost = ""
        if to_the_right:
            cost = actions.read_value(sorted(to_the_right)[0][1])
        return actions.read_value(combo).strip(), cost

    # --- writing -------------------------------------------------------------

    def confirm_vat_mode(self, expected: str = "With VAT") -> str:
        combo = find(self.window, control_type="ComboBox", name="VAT")
        actual = actions.read_value(combo)
        if actual != expected:
            actions.select_combo(combo, expected, what="VAT mode")
        return expected

    # --- helpers -------------------------------------------------------------

    def _combo_on_row_with(self, element):
        """The one ComboBox sharing a horizontal row with the given control.

        Several of this form's dropdowns carry no accessible name at all: the price mode
        beside the Date, and the payment method beside the paid checkbox. Both sit on the
        same row as something that *is* named, which is the same anchor-relative idea
        `labelled` uses, rotated to take a control rather than a label as the anchor.
        """
        from src.uia.locator import iter_descendants

        box = element.rectangle()
        middle = (box.top + box.bottom) / 2

        on_the_row = []
        for candidate in iter_descendants(self.window):
            if candidate.element_info.control_type != "ComboBox":
                continue
            rect = candidate.rectangle()
            if rect.top <= middle <= rect.bottom:
                on_the_row.append((rect.left, candidate))

        if not on_the_row:
            raise LookupError("no ComboBox on the same row as the anchor control")
        return sorted(on_the_row, key=lambda pair: pair[0])[0][1]
