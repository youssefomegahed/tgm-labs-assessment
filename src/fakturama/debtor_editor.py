"""The New Debtor editor.

Opened from the left panel's New Contact while the Order tab stays open behind it. The
Order tab shows as "*New Order" while it holds unsaved changes, which is a handy
confirmation that we did not lose it.
"""

import time

from src.models import Address, Debtor
from src.uia import actions
from src.uia.locator import find, find_optional, labelled

TAB = "New Debtor"

# Fakturama's own wording for the two roles an address can carry.
INVOICE_ROLE = "invoice address"
DELIVERY_ROLE = "delivery address"
BOTH_ROLES = "invoice address;delivery address"


class DebtorEditor:
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
        actions.click(find(self.window, control_type="TabItem", name=title))
        time.sleep(0.5)

    def fill_address(self, address: Address, contact_email: str = "",
                     contact_phone: str = "") -> None:
        """Street, ZIP, City, Country, and the contact details that sit beside them."""
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
        """
        actions.click(find(self.window, control_type="Button", name="+"))
        time.sleep(1)

    # --- miscellaneous and payment -------------------------------------------

    def set_alias_and_discount(self, alias: str) -> None:
        self.open_tab("Miscellaneous")
        element = find_optional(self.window, control_type="Edit", name="Alias name",
                                timeout=5)
        if element is not None and alias:
            actions.set_text(element, alias, what="Alias name")

    def select_payment_method(self, method: str) -> bool:
        """Choose the payment method, saying whether it was available at all."""
        self.open_tab("Payment")
        combo = find_optional(self.window, control_type="ComboBox", name="Payment",
                              timeout=5)
        if combo is None:
            return False
        try:
            actions.select_combo(combo, method, what="Payment Method")
            return True
        except Exception:
            return False
