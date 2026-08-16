"""Stage 1 of the brief: open a New Order and set its header.

Deliberately does not touch the proposed document number. Fakturama allocates it and the
brief says to leave it alone.
"""

import time

from src.fakturama.order_editor import OrderEditor
from src.models import OrderData

STAGE = "order"


def begin(main_window, order: OrderData, log=print) -> OrderEditor:
    """Open the Order editor and fill in everything that does not need master data."""
    main_window.focus()
    main_window.click_toolbar("order")

    # Eclipse takes a while to build the editor under emulation, so wait on the tab
    # appearing rather than on a fixed sleep.
    from src.uia.locator import wait_until

    wait_until(lambda: main_window.has_tab(OrderEditor.TAB), timeout=90,
               description="the New Order editor")
    time.sleep(2)

    editor = OrderEditor(main_window)
    log(f"new Order editor open, proposed number {editor.document_number!r}")

    # Price mode first, against the brief's ordering, which sets the Date at 1.5 and the
    # price mode at 1.7. Switching Net/Gross makes Fakturama recalculate the document,
    # and that recalculation resets the Date back to today. Following the brief's order
    # produced an Order that verified as Jul 14 at the moment of writing and held Aug 16
    # by the end of the stage.
    editor.set_price_mode("Net")
    log("price mode Net")

    log(f"vat mode {editor.confirm_vat_mode()!r}")

    editor.set_date(order.order_date)
    log(f"date {editor.order_date!r}")

    editor.set_customer_reference(order.external_reference)
    log(f"cust.ref. {editor.customer_reference!r}")

    confirm_header(editor, order, log)
    return editor


def complete_and_save(main_window, order: OrderData, log=print) -> dict:
    """Stage 4: confirm the Order, save it once, and verify it was stored.

    Returns the row Fakturama lists for it, which is the evidence that the save landed.
    """
    from src.errors import ManualReviewRequired
    from src.fakturama.documents_view import DocumentsView

    main_window.focus()
    main_window.focus_editor(OrderEditor.TAB)
    editor = OrderEditor(main_window)

    totals = editor.totals()
    log(f"order totals {totals}")

    _confirm_totals(totals, order, log)
    _confirm_no_order_level_adjustments(editor, totals, log)

    # Read the number Fakturama allocated before saving, so the row can be found by it
    # afterwards. The Cust.Ref. cannot do that job: run the same document twice and the
    # list holds two Orders carrying it.
    number = editor.document_number
    log(f"about to save {number!r}")

    main_window.save()
    time.sleep(4)
    log("saved the Order once")

    # The editor would happily show what we typed. Ask the application instead.
    documents = DocumentsView(main_window)
    documents.open()
    row = documents.find_document(number)
    if row is None:
        raise ManualReviewRequired(
            f"saved the Order but no document numbered {number!r} is listed",
            stage=STAGE,
        )
    log(f"listed as {row}")

    from src.matching import cell_matches

    if not cell_matches(row.get("Cust.Ref.", ""), order.external_reference):
        raise ManualReviewRequired(
            f"the saved Order {number!r} lists Cust.Ref. {row.get('Cust.Ref.')!r}, "
            f"expected {order.external_reference!r}",
            stage=STAGE,
        )

    state = (row.get("State") or "").strip().lower()
    if state and "open" not in state:
        raise ManualReviewRequired(
            f"the saved Order is in state {row.get('State')!r}, expected open",
            stage=STAGE,
        )
    return row


def _confirm_no_order_level_adjustments(editor, totals: dict, log) -> None:
    """Step 4.2: the overall Discount stays at 0% and Shipping stays free.

    Asserted rather than assumed, and worth the few lines. Neither is ever written by
    this flow, so a non-zero value here means something else moved them: a stray
    keystroke landing on the wrong field, or a debtor carrying a default discount. Both
    change what the customer is billed while leaving every line correct, which is exactly
    the kind of wrong that survives a glance at the item table.

    The brief allows order-level values when the image supplies them. This document
    supplies none, so anything other than zero is a discrepancy.
    """
    from src.errors import ManualReviewRequired
    from src.uia.actions import _as_number

    wrong = []

    discount = _as_number(totals.get("discount", ""))
    if discount is None or discount != 0:
        wrong.append(f"the overall Discount shows {totals.get('discount')!r}, "
                     f"expected 0%")

    shipping_name, shipping_cost = editor.shipping()
    if _as_number(shipping_cost) != 0:
        wrong.append(f"Shipping costs {shipping_cost!r}, expected 0.00")
    if shipping_name and "free" not in shipping_name.casefold():
        wrong.append(f"Shipping is {shipping_name!r}, expected free of shipping costs")

    if wrong:
        raise ManualReviewRequired(
            "the Order carries order-level values the document does not:\n  "
            + "\n  ".join(wrong),
            stage=STAGE,
        )
    log(f"discount {totals.get('discount')!r}, shipping {shipping_name!r} at "
        f"{shipping_cost!r}")


def _confirm_totals(totals: dict, order: OrderData, log) -> None:
    """Check the Order's own totals against the document before saving.

    A mismatch here is the point of the whole exercise: it means what Fakturama holds is
    not what the customer sent, and saving it would commit wrong numbers.
    """
    from src.errors import ManualReviewRequired
    from src.uia.actions import _as_number

    expected = {
        "total_net": order.net_total,
        "vat": order.vat_total,
        "total": order.gross_total,
    }

    wrong = []
    for key, want in expected.items():
        shown = _as_number(totals.get(key, ""))
        if shown is None or shown != want:
            wrong.append(f"{key}: shows {totals.get(key)!r}, document says {want}")

    if wrong:
        raise ManualReviewRequired(
            "the Order does not match the document before saving:\n  "
            + "\n  ".join(wrong),
            stage=STAGE,
        )
    log("totals match the document")


def confirm_header(editor: OrderEditor, order: OrderData, log=print) -> None:
    """Re-read the header at the end of the stage.

    Each field was verified as it was written, but a later step can undo an earlier one,
    which is exactly what the price mode did to the Date. Verifying once more at the end
    is what catches that class of interaction.
    """
    from src.errors import VerificationFailed
    from src.fakturama.order_editor import format_date

    expected_date = format_date(order.order_date)
    if editor.order_date != expected_date:
        raise VerificationFailed("Order date", expected_date, editor.order_date)

    if editor.customer_reference != order.external_reference:
        raise VerificationFailed("Cust.Ref.", order.external_reference,
                                 editor.customer_reference)

    log("header re-checked after all writes")
