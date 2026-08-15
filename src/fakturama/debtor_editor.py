"""The New Debtor editor.

Opened from the left panel's New Contact while the Order tab stays open behind it. The
Order tab shows as "*New Order" while it holds unsaved changes, which is a handy
confirmation that we did not lose it.
"""

import time

from src.models import Address, Debtor
from src.uia import actions
from src.uia.locator import find, find_optional, labelled

class DebtorEditor:
    TAB = "New Debtor"

    # Fakturama's own wording for the roles an address can carry.
    INVOICE_ROLE = "invoice address"
    DELIVERY_ROLE = "delivery address"
    BOTH_ROLES = "invoice address;delivery address"

    def __init__(self, main_window):
        self.main = main_window
        self.window = main_window.window

    # --- header --------------------------------------------------------------

    @property
    def customer_id(self) -> str:
        """Fakturama proposes this and the brief says to leave it alone."""
        return actions.read_value(find(self.window, control_type="Edit", name="Customer ID"))

    def set_names(self, debtor: Debtor) -> None:
        actions.set_text(
            find(self.window, control_type="Edit", name="Company"),
            debtor.company,
            what="Company",
        )
        # One label, "First Name Last Name", in front of two anonymous boxes.
        actions.set_text(
            labelled(self.window, "First Name Last Name", index=0),
            debtor.contact.first_name,
            what="First Name",
        )
        actions.set_text(
            labelled(self.window, "First Name Last Name", index=1),
            debtor.contact.last_name,
            what="Last Name",
        )
        # Salutation is left at --- when the source does not supply one, per the brief.

    # --- addresses -----------------------------------------------------------

    def open_tab(self, title: str) -> None:
        actions.select_tab(find(self.window, control_type="TabItem", name=title),
                           what=title)

    def fill_address(self, address: Address, contact_email: str = "",
                     contact_phone: str = "", company: str = "") -> None:
        """Street, ZIP, City, Country, and the contact details that sit beside them.

        `additional name` carries the name heading the address block when it is not just
        the company again. Our sample's delivery block reads "Northstar Office
        Warehouse", and dropping it both loses real data and appears to be what made
        Fakturama reject the address as invalid on save.
        """
        if address.name and address.name != company:
            actions.set_text(
                find(self.window, control_type="Edit", name="additional name"),
                address.name,
                what="additional name",
            )

        actions.set_text(
            find(self.window, control_type="Edit", name="Street"),
            address.street,
            what="Street",
        )
        # "ZIP - City" heads two boxes; reading order decides which is which.
        actions.set_text(labelled(self.window, "ZIP - City", index=0),
                         address.zip_code, what="ZIP")
        actions.set_text(labelled(self.window, "ZIP - City", index=1),
                         address.city, what="City")

        actions.select_combo(
            find(self.window, control_type="ComboBox", name="Country"),
            address.country,
            what="Country",
        )

        if contact_email:
            actions.set_text(find(self.window, control_type="Edit", name="E-Mail"),
                             contact_email, what="E-Mail")
        if contact_phone:
            actions.set_text(find(self.window, control_type="Edit", name="Telephone"),
                             contact_phone, what="Telephone")

    def set_address_role(self, role: str) -> None:
        """Assign the Invoice and/or Delivery role to the address on screen."""
        actions.set_text(labelled(self.window, "address type"), role,
                         what="address type")

    def add_address(self) -> None:
        """The + beside the address tabs, for a delivery address that differs.

        The brief only spells out the case where billing and delivery are the same and
        the Main address carries both roles. Our sample ships to a different site, so it
        needs a second address.

        Clicking + creates the tab without bringing it to the front, and that is not a
        cosmetic problem. Text fields can still be written, because the value pattern
        does not care whether a control is visible, but a dropdown cannot be expanded on
        a page that is not showing. The symptom was the new address taking its Street,
        ZIP and City happily and then silently keeping the default Country.
        """
        actions.click(find(self.window, control_type="Button", name="+"))
        time.sleep(1.5)
        self.focus_last_address_tab()

    def focus_last_address_tab(self) -> None:
        """Bring the right-most address tab to the front.

        Found by position rather than by name because the tabs are "Main address" and
        then "additional address #1", "#2" and so on, and the numbering depends on how
        many exist.
        """
        from src.uia.locator import find_all

        tabs = [
            tab for tab in find_all(self.window, control_type="TabItem")
            if "address" in (tab.element_info.name or "").casefold()
        ]
        if not tabs:
            raise LookupError("no address tabs found")

        rightmost = max(tabs, key=lambda tab: tab.rectangle().left)
        actions.select_tab(rightmost, what=rightmost.element_info.name)

    # --- miscellaneous and payment -------------------------------------------

    def set_miscellaneous(self, alias: str) -> None:
        """Alias, a zero discount and Net pricing, all on the Miscellaneous tab.

        The brief calls step 2.10 "open Payment", which reads like a tab. It is a field
        on this same tab, next to Discount.
        """
        self.open_tab("Miscellaneous")

        if alias:
            actions.set_text(find(self.window, control_type="Edit", name="Alias name"),
                             alias, what="Alias name")

        actions.set_text(find(self.window, control_type="Edit", name="Discount"),
                         "0%", what="Discount")
        actions.select_combo(
            find(self.window, control_type="ComboBox", name="Net or Gross"),
            "Net", what="Net or Gross",
        )

    def select_payment_method(self, method: str) -> bool:
        """Choose the payment method, saying whether it was available at all.

        Returning False rather than raising is deliberate: a missing method is not an
        error, it is the signal to go and create it and come back.
        """
        self.open_tab("Miscellaneous")
        combo = find_optional(self.window, control_type="ComboBox", name="Payment",
                              timeout=5)
        if combo is None:
            return False
        try:
            actions.select_combo(combo, method, what="Payment Method")
            return True
        except Exception:
            return False
