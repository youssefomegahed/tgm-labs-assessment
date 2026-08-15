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

    editor.set_date(order.order_date)
    log(f"date {editor.order_date!r}")

    editor.set_customer_reference(order.external_reference)
    log(f"cust.ref. {editor.customer_reference!r}")

    editor.set_price_mode("Net")
    log("price mode Net")

    log(f"vat mode {editor.confirm_vat_mode()!r}")
    return editor
