"""The New product editor, reached from the left panel's New product.

Only opened once the line's VAT rate exists, because the rate has to be in the VAT
dropdown for this form to select it.
"""

import time

from src.models import LineItem
from src.uia import actions
from src.uia.locator import find, labelled

TAB = "New product"


class ProductEditor:
    def __init__(self, main_window):
        self.main = main_window
        self.window = main_window.window

    def create(self, item: LineItem) -> None:
        """Fill and save a Product from an order line.

        The brief is specific about which values come from where: the item number and
        description from the line, a gross price derived from the net price and the VAT
        rate, and zero for cost price and stock. Category, GTIN, supplier code,
        allowance, the picture and the user defined fields are left alone.
        """
        self._open_blank_editor()

        # Bring the editor to the front before looking for its fields. SWT does not
        # realize a hidden tab's page, so the fields are absent from the tree until the
        # tab is actually in front.
        self.main.focus_editor(TAB)
        find(self.window, control_type="Edit", name="Item Number", timeout=45)
        # The form is taller than the editor pane, and controls below its edge take text
        # but not clicks.
        self.main.maximize_editor_area()

        try:
            actions.set_text(find(self.window, control_type="Edit", name="Item Number"),
                             item.sku, what="Item Number")

            # Name and Description both take the line's description, per the brief.
            actions.set_text(find(self.window, control_type="Edit", name="Name"),
                             item.description, what="product Name")
            actions.set_text(find(self.window, control_type="Edit", name="Description"),
                             item.description, what="product Description")

            # Unnamed money fields sitting beside their labels. Real keystrokes,
            # because the formatted ones ignore the value pattern.
            actions.set_text(labelled(self.window, "Price (gross)"),
                             f"{item.master_gross_price:f}", keystrokes=True,
                             what="Price (gross)")
            actions.set_text(labelled(self.window, "cost price (net)"),
                             "0.00", keystrokes=True, what="cost price (net)")

            actions.select_combo(find(self.window, control_type="ComboBox", name="VAT"),
                                 item.vat_rate_name, what="product VAT")

            actions.set_text(find(self.window, control_type="Edit", name="Stock"),
                             "0.00", keystrokes=True, what="Stock")

            self.main.save()
            time.sleep(3)
        finally:
            self.main.restore_editor_area()

    def _open_blank_editor(self, attempts: int = 3) -> None:
        """Open a fresh New product tab, waiting for it to actually appear.

        Saving renames the tab from "New product" to the product's own name, so on the
        second and later products the navigation entry has to build a new tab rather
        than focus an existing one. That takes longer than focusing does, and clicking
        the entry again while it is still building achieves nothing, so this waits and
        only re-clicks if the tab never arrived.
        """
        from src.uia.locator import wait_until

        for attempt in range(attempts):
            self.main.open_navigation("New product")
            try:
                wait_until(lambda: self.main.has_tab(TAB), timeout=30,
                           description="the New product editor")
                return
            except Exception:
                if attempt == attempts - 1:
                    raise
                time.sleep(3)
