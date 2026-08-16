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
