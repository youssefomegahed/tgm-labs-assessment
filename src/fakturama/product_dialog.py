"""The "Select a product" dialog, opened from the Order's Items area.

The brief's existence check for a Product, matched on the SKU alone.
"""

from src.fakturama.selector_dialog import SelectorDialog


class ProductDialog(SelectorDialog):
    TITLE = "Select a product"

    # As shown in the brief's figure 5. Item No. is the only one that decides a match:
    # description and price are allowed to differ from the order line.
    COLUMNS = ["Item No.", "Name", "Description", "Stock", "Price", "VAT"]
