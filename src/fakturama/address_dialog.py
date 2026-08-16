"""The "Select the address" dialog, opened from the Order.

This is the brief's existence check for a Debtor. The mechanics live in SelectorDialog,
which the product selector shares.
"""

from src.fakturama.selector_dialog import SelectorDialog


class AddressDialog(SelectorDialog):
    TITLE = "Select the address"

    # The columns the brief names as deciding a match, in the order they appear. Note
    # the list holds one row per address rather than per debtor, so a debtor with a
    # separate delivery address may surface with no company and a different postcode.
    # See matching.debtor_candidate for what the flow does about that.
    COLUMNS = ["No.", "First Name", "Name", "Company", "ZIP", "City"]
