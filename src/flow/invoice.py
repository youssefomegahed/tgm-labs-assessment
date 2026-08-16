"""Stage 5 of the brief: the linked Invoice and its payment status.

The Invoice is deliberately not created from the toolbar. The brief is emphatic about
this and it is not a style preference: only the Order's own "Create a follow-up document"
action carries the relationship across, and a toolbar Invoice is a new document that
happens to look the same. Nothing in the finished Invoice would show the difference, so
this is exactly the kind of mistake that survives review.

What this stage writes is small: a payment method, and on a paid document a date and a
value. What it checks is not, because everything else on the Invoice was copied by
Fakturama rather than typed by us, and a copy that silently dropped a field is the
failure worth catching.
"""

import time

from src.errors import ManualReviewRequired
from src.fakturama.documents_view import DocumentsView
from src.fakturama.invoice_editor import InvoiceEditor
from src.fakturama.order_editor import OrderEditor
from src.models import OrderData
from src.uia.actions import _as_number
from src.uia.locator import wait_until

STAGE = "invoice"


def create_and_complete(main_window, order: OrderData, order_row: dict,
                        log=print) -> dict:
    """From a saved Order to a saved, verified Invoice.

    `order_row` is what Data > Documents listed for the Order in stage 4, and it is
    carried in so the final check can prove the Order is still there and unchanged
    beside its new Invoice.
    """
    editor = _open_from_order(main_window, order_row, log)

    _confirm_copied(editor, order, log)

    editor.select_payment_method(order.payment.method)
    log(f"payment method {editor.payment_method!r}")

    _apply_payment_status(editor, order, log)

    number = editor.document_number
    main_window.save()
    time.sleep(4)
    log(f"saved the Invoice once, as {number!r}")

    return _confirm_saved(main_window, order, order_row, number, log)


def _open_from_order(main_window, order_row: dict, log) -> InvoiceEditor:
    """Step 4.6 and 4.7: the follow-up Invoice, and waiting for its editor.

    The Order tab is no longer called "New Order" by the time this runs. Saving renames
    it to the document number Fakturama allocated, so stage 4 leaves a tab called
    something like "PO000001" and looking for the old name times out on an editor that is
    plainly on screen. The number comes from the row stage 4 read back out of Data >
    Documents, which is the same place the save was confirmed.
    """
    main_window.focus()

    number = (order_row.get("Document") or "").strip().rstrip(".…")
    for title in [number, OrderEditor.TAB]:
        if not title:
            continue
        try:
            main_window.focus_editor(title)
            log(f"back on the saved Order, tab {title!r}")
            break
        except Exception:
            continue
    else:
        raise ManualReviewRequired(
            f"cannot find the saved Order's editor tab; looked for {number!r} and "
            f"{OrderEditor.TAB!r}", stage=STAGE)

    order_editor = OrderEditor(main_window)
    order_editor.create_follow_up("Invoice")
    log("clicked Invoice in the Order's follow-up group")

    wait_until(lambda: main_window.has_tab(InvoiceEditor.TAB), timeout=90,
               description="the linked Invoice editor")
    time.sleep(3)

    main_window.focus_editor(InvoiceEditor.TAB)
    editor = InvoiceEditor(main_window)
    log(f"linked Invoice open, proposed number {editor.document_number!r}")
    return editor


def _confirm_copied(editor: InvoiceEditor, order: OrderData, log) -> None:
    """Step 5.1: everything Fakturama carried over has to match the source document.

    The invoice number, invoice date and service date are deliberately not checked
    against anything: the brief says to leave Fakturama's own proposals alone, and a
    value we neither supplied nor constrained is not ours to have an opinion about. They
    are read and logged so a run's output shows what was accepted.
    """
    log(f"invoice date {editor.invoice_date!r}, service date {editor.service_date!r}")

    wrong = []

    if editor.customer_reference != order.external_reference:
        wrong.append(f"Cust.Ref. is {editor.customer_reference!r}, "
                     f"expected {order.external_reference!r}")

    invoice_address = editor.address_block("Invoice address")
    for field in (order.debtor.company, order.debtor.billing.street,
                  order.debtor.billing.zip_code, order.debtor.billing.city):
        if field and field not in invoice_address:
            wrong.append(f"the invoice address is missing {field!r}")

    if editor.has_address_tab("Delivery address"):
        delivery = editor.address_block("Delivery address")
        # Street, ZIP and city, and deliberately not the name heading the source
        # document's delivery block. That name, "Northstar Office Warehouse", is stored
        # on the debtor's second address as its `additional name` and verified there when
        # stage 2 writes it, but a document's address block renders the debtor and the
        # address's street, postcode, city and country, and never the additional name.
        # Asserting it here would be asserting something Fakturama does not display.
        #
        # The three that are checked are what actually distinguishes this address from
        # the billing one, which is the thing worth being sure of: Beusselstrasse 44 and
        # 10553, not Friedrichstrasse 88 and 10117.
        for field in (order.debtor.delivery.street, order.debtor.delivery.zip_code,
                      order.debtor.delivery.city):
            if field and field not in delivery:
                wrong.append(f"the delivery address is missing {field!r}")
        if order.debtor.billing.street in delivery:
            wrong.append("the delivery address shows the billing street, so the Invoice "
                         "is carrying the wrong one of the debtor's addresses")
    elif not order.debtor.delivery_is_billing:
        wrong.append("the source document has a separate delivery address and the "
                     "Invoice shows no Delivery address tab")

    totals = editor.totals()
    for key, want in (("total_net", order.net_total), ("vat", order.vat_total),
                      ("total", order.gross_total)):
        shown = _as_number(totals.get(key, ""))
        if shown is None or shown != want:
            wrong.append(f"{key}: shows {totals.get(key)!r}, document says {want}")

    if wrong:
        raise ManualReviewRequired(
            "the linked Invoice does not match the source document:\n  "
            + "\n  ".join(wrong),
            stage=STAGE,
        )

    log("Cust.Ref., addresses and totals all carried over correctly")


def _apply_payment_status(editor: InvoiceEditor, order: OrderData, log) -> None:
    """Step 5.3, and its other half.

    A document that does not say PAID gets nothing invented for it. That is worth being
    explicit about rather than leaving as an absent branch, because a payment date and a
    value on an unpaid invoice is not a cosmetic error: it says a customer has paid when
    they have not.
    """
    if not order.payment.is_paid:
        if editor.is_paid:
            raise ManualReviewRequired(
                "the source document is unpaid and the Invoice opened already marked "
                "paid", stage=STAGE)
        log("document is unpaid, leaving paid clear with no date and no value")
        return

    if order.payment.paid_on is None:
        raise ManualReviewRequired(
            "the source document says PAID but carries no payment date", stage=STAGE)

    # The full invoice total, as the brief requires, taken from the document rather than
    # from the editor: the two were just checked against each other, and the document is
    # the thing being recorded.
    editor.mark_paid(order.payment.paid_on, f"{order.gross_total:f}")
    log(f"marked paid on {order.payment.paid_on} for {order.gross_total}")


def _confirm_saved(main_window, order: OrderData, order_row: dict, number: str,
                   log) -> dict:
    """Step 5.5: ask the application what it stored, not the editor what we typed.

    Both rows are checked, and both by document number rather than by Cust.Ref., because
    the reference is not unique across runs. The Invoice has to be there with the right
    total and state, and the source Order has to still be there, still open, still
    carrying the same total it had before. An Invoice that quietly consumed or altered
    its Order would otherwise look like a clean run.
    """
    documents = DocumentsView(main_window)
    documents.open()
    rows = documents.rows(save_to="runs/documents-final.png")

    from src.matching import cell_matches

    invoice = next((row for row in rows
                    if cell_matches(row.get("Document", ""), number)), None)
    if invoice is None:
        raise ManualReviewRequired(
            f"saved the Invoice but no document numbered {number!r} is listed",
            stage=STAGE)
    log(f"Invoice listed as {invoice}")

    if not cell_matches(invoice.get("Cust.Ref.", ""), order.external_reference):
        raise ManualReviewRequired(
            f"the saved Invoice lists Cust.Ref. {invoice.get('Cust.Ref.')!r}, expected "
            f"{order.external_reference!r}", stage=STAGE)

    shown = _as_number(invoice.get("Total", ""))
    if shown is None or shown != order.gross_total:
        raise ManualReviewRequired(
            f"the listed Invoice total is {invoice.get('Total')!r}, and the document "
            f"says {order.gross_total}", stage=STAGE)

    expected_state = "paid" if order.payment.is_paid else "unpaid"
    state = (invoice.get("State") or "").strip().lower()
    if state and expected_state not in state:
        raise ManualReviewRequired(
            f"the listed Invoice is in state {invoice.get('State')!r}, expected "
            f"{expected_state}", stage=STAGE)

    # The source Order, found by its own number for the same reason.
    order_number = (order_row.get("Document") or "").strip()
    still_there = next((row for row in rows
                        if cell_matches(row.get("Document", ""), order_number)), None)
    if still_there is None:
        raise ManualReviewRequired(
            f"the source Order {order_number!r} is no longer listed beside its Invoice",
            stage=STAGE)

    was, now = order_row.get("Total"), still_there.get("Total")
    if _as_number(was or "") != _as_number(now or ""):
        raise ManualReviewRequired(
            f"the source Order's total changed from {was!r} to {now!r} when the "
            f"Invoice was created", stage=STAGE)

    order_state = (still_there.get("State") or "").strip().lower()
    if order_state and "open" not in order_state:
        raise ManualReviewRequired(
            f"the source Order is in state {still_there.get('State')!r} after invoicing, "
            f"expected it to remain open", stage=STAGE)

    log(f"Invoice {number} is {invoice.get('State')!r} for {invoice.get('Total')}; "
        f"Order {order_number} still {still_there.get('State')!r} for {now}")
    return invoice
