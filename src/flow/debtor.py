"""Stage 2 of the brief: select or create the Debtor.

Reads like the brief, with one deliberate difference in ordering. The brief has you keep
the Debtor editor open, go and create a missing payment method, then come back and select
it. That last step cannot work: the Debtor's Payment dropdown is built when the editor
opens and never refreshes, so a method created afterwards is simply not in the list.

So the payment method is resolved before the Debtor editor is opened. Same end state,
and it avoids the two bad alternatives, which are reopening the editor and losing what
was typed, or saving a Debtor pointing at the wrong payment method.
"""

import time

from src.errors import ManualReviewRequired
from src.fakturama.address_dialog import AddressDialog
from src.fakturama.debtor_editor import DebtorEditor
from src.fakturama.order_editor import OrderEditor
from src.fakturama.payment_editor import PaymentEditor
from src.matching import debtor_candidate, missing_from_address_block, resolve_one
from src.models import OrderData

STAGE = "debtor"


def resolve(main_window, order: OrderData, log=print) -> None:
    """Get the Order pointing at the right Debtor, creating one if there is not one."""
    if _try_select(main_window, order, log):
        return

    log("no exact Debtor, taking the creation branch")

    # Before the editor opens, not after. See the module docstring.
    created = PaymentEditor(main_window).ensure(order.payment.method)
    log(f"payment method {order.payment.method!r} "
        f"{'created' if created else 'already existed'}")

    _create(main_window, order, log)

    if not _try_select(main_window, order, log):
        raise ManualReviewRequired(
            "saved the Debtor but it cannot be selected from the Order afterwards",
            stage=STAGE,
        )


def _try_select(main_window, order: OrderData, log) -> bool:
    """Use the Order's own address selector as the existence check.

    Returns True when a single exact Debtor was selected. Raises when the results are
    ambiguous, because choosing between them is a person's job.
    """
    # The grid is read from a screen region derived from control positions, so the
    # window must be maximized and unobstructed before that region means anything.
    main_window.focus()
    main_window.focus_editor(OrderEditor.TAB)
    OrderEditor(main_window).open_address_selector()

    dialog = AddressDialog()
    # Search by surname rather than company: the delivery row of a multi-address debtor
    # carries no company at all, so a company search cannot surface it.
    dialog.search(order.debtor.contact.last_name)
    rows = dialog.rows()
    log(f"address selector returned {len(rows)} row(s)")

    found = resolve_one(
        rows, lambda row: debtor_candidate(row, order.debtor),
        what=f"Debtor {order.debtor.contact.first_name} "
             f"{order.debtor.contact.last_name}",
        stage=STAGE,
    )

    if found is None:
        dialog.cancel()
        return False

    dialog.select(rows.index(found))
    dialog.ok()
    time.sleep(2)
    log(f"selected candidate {found}")

    # The name got us here; the address the Order now shows is what confirms it really
    # is our customer. Anything missing means we picked the wrong person.
    block = OrderEditor(main_window).address_block
    missing = missing_from_address_block(block, order.debtor)
    if missing:
        raise ManualReviewRequired(
            "the selected Debtor's invoice address does not match the document. "
            f"Missing: {', '.join(missing)}. Address shown: {block!r}",
            stage=STAGE,
        )

    log("invoice address matches the document")
    return True


def _create(main_window, order: OrderData, log) -> None:
    """Fill and save a new Debtor, leaving the Order tab alone."""
    debtor = order.debtor

    main_window.open_navigation("New Contact")
    editor = DebtorEditor(main_window)
    log(f"new Debtor editor open, proposed id {editor.customer_id!r}")

    # The Debtor form is taller than the editor pane, and the rows below the pane's
    # edge accept text but not clicks. Maximizing the editor makes the whole form real.
    main_window.maximize_editor_area()

    try:
        editor.set_names(debtor)
        editor.open_tab("Addresses")
        editor.fill_address(
            debtor.billing,
            contact_email=debtor.contact.email,
            contact_phone=debtor.contact.phone,
            company=debtor.company,
        )

        if debtor.delivery_is_billing:
            # One address carrying both roles, the case the brief walks through.
            editor.set_address_role(invoice=True, delivery=True)
            log("billing and delivery match, main address carries both roles")
        else:
            editor.set_address_role(invoice=True, delivery=False)
            editor.add_address()
            editor.fill_address(debtor.delivery, company=debtor.company)
            editor.set_address_role(invoice=False, delivery=True)
            log("delivery differs, added a second address for it")

        editor.set_miscellaneous(debtor.alias)
        if not editor.select_payment_method(order.payment.method):
            raise ManualReviewRequired(
                f"payment method {order.payment.method!r} is not offered even though "
                f"it was resolved before this editor opened",
                stage=STAGE,
            )
        log(f"payment method {order.payment.method!r} selected")

        main_window.save()
        time.sleep(3)
        log("saved the Debtor once")
    finally:
        # The bottom panel has to come back: selectors and verification live there.
        main_window.restore_editor_area()
