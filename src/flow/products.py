"""Stage 3 of the brief: select or create each Product, in source order.

The same resolve-or-create shape as the Debtor, with one extra step in front: a Product
cannot be created until its VAT rate exists, because the rate has to be in the form's
VAT dropdown.
"""

import time

from src.errors import ManualReviewRequired
from src.fakturama.order_editor import OrderEditor
from src.fakturama.product_dialog import ProductDialog
from src.fakturama.product_editor import ProductEditor
from src.fakturama.vat_editor import VatEditor
from src.matching import product_matches, resolve_one
from src.models import LineItem, OrderData

STAGE = "products"


def resolve_all(main_window, order: OrderData, log=print) -> None:
    """Every line's Product on the Order, created where missing."""
    for item in order.items:
        log(f"line {item.position}: {item.sku}")
        resolve(main_window, item, log)


def resolve(main_window, item: LineItem, log=print) -> None:
    if _try_select(main_window, item, log):
        return

    log(f"  no Product {item.sku!r}, taking the creation branch")

    # Before the product editor opens, not after: its VAT dropdown is built when the
    # editor opens, the same way the Debtor's payment dropdown was.
    created = VatEditor(main_window).ensure(item)
    log(f"  VAT rate {item.vat_rate_name!r} "
        f"{'created' if created else 'already existed'}")

    ProductEditor(main_window).create(item)
    log(f"  saved Product {item.sku!r}")

    if not _try_select(main_window, item, log):
        raise ManualReviewRequired(
            f"saved Product {item.sku!r} but it cannot be selected from the Order "
            f"afterwards",
            stage=STAGE,
        )


def _try_select(main_window, item: LineItem, log) -> bool:
    """Use the Order's own product selector as the existence check.

    Returns True when one exact SKU was selected. Raises when several match, because
    choosing between them is a person's job.
    """
    # The grid is read from a screen region derived from control positions, so the
    # window must be maximized and unobstructed before that region means anything.
    main_window.focus()
    main_window.focus_editor(OrderEditor.TAB)
    OrderEditor(main_window).open_product_selector()

    dialog = ProductDialog()
    dialog.search(item.sku)
    rows = dialog.rows()
    log(f"  product selector returned {len(rows)} row(s)")

    found = resolve_one(
        rows, lambda row: product_matches(row, item.sku),
        what=f"Product {item.sku!r}", stage=STAGE,
    )

    if found is None:
        dialog.cancel()
        return False

    dialog.choose(rows.index(found))
    time.sleep(2)
    log(f"  selected {found}")
    return True
