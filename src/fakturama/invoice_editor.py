"""The linked Invoice editor, reached from the saved Order's follow-up buttons.

Every locator here was read off the live editor rather than guessed, because the paid
row is the one part of this form that changes shape as it is used. Unticked it reads

    [ ] paid  [payment method v]  Due Days [  ]  Pay Until [        ]

and ticking it replaces the right-hand half with

    [x] paid  [payment method v]  at [          ]  Value [      ]

So the payment date field only exists once the box is ticked, and looking for it first
finds the Pay Until box instead, which is a different date with a different meaning.
`mark_paid` ticks first and looks second for exactly that reason.

Two of the three controls carry no accessible name. `Value` does. The payment method is
the only ComboBox on the paid row, and the payment date is the Edit immediately right of
a two-letter label, "at".
"""

import time

from datetime import date

from src.errors import VerificationFailed
from src.fakturama.document_editor import DocumentEditor, format_date
from src.uia import actions
from src.uia.locator import find, labelled


class InvoiceEditor(DocumentEditor):
    TAB = "New Invoice"

    # --- reading -------------------------------------------------------------

    @property
    def invoice_date(self) -> str:
        return actions.read_value(labelled(self.window, "Date"))

    @property
    def service_date(self) -> str:
        return actions.read_value(labelled(self.window, "Service date"))

    @property
    def order_date(self) -> str:
        return actions.read_value(labelled(self.window, "Order Date"))

    @property
    def is_paid(self) -> bool:
        return actions.is_checked(self._paid_checkbox())

    @property
    def payment_method(self) -> str:
        return actions.read_value(self._payment_combo()).strip()

    # --- writing -------------------------------------------------------------

    def select_payment_method(self, method: str) -> None:
        """Set the Invoice's payment method, or say what it could offer instead.

        The brief stops the run when the required method is unavailable rather than
        letting a different one through, which matters because the method is what the
        customer is being told to pay by.
        """
        combo = self._payment_combo()
        if actions.read_value(combo).strip() == method:
            return
        actions.select_combo(combo, method, what="Invoice payment method")

    def mark_paid(self, paid_on: date, value: str) -> None:
        """Tick paid, then set the payment date and the value.

        In that order because the two fields do not exist until the box is ticked. The
        brief is equally firm about the other branch: an unpaid invoice gets no invented
        date and no invented value, which is why this is only ever called when the
        source document says PAID.
        """
        box = self._paid_checkbox()
        actions.set_checkbox(box, True, what="paid")
        time.sleep(1.5)

        # Real keystrokes, and the digits only. The date fields on this form are
        # segmented spinners: a formatted string scatters across the month, day and year
        # segments, which is how "Jul 14, 2026" once became "Aug 20, 0026".
        field = labelled(self.window, "at")
        wanted = format_date(paid_on)
        digits = f"{paid_on.month:02d}{paid_on.day:02d}{paid_on.year:04d}"

        for _ in range(3):
            field = labelled(self.window, "at")
            field.set_focus()
            field.type_keys("{HOME}", pause=0.05)
            field.type_keys(digits, pause=0.12)
            field.type_keys("{TAB}")
            time.sleep(0.8)
            if actions.read_value(labelled(self.window, "at")) == wanted:
                break
        else:
            raise VerificationFailed("payment date", wanted,
                                     actions.read_value(labelled(self.window, "at")))

        actions.set_text(find(self.window, control_type="Edit", name="Value"),
                         value, keystrokes=True, what="payment Value")

    # --- internals -----------------------------------------------------------

    def _paid_checkbox(self):
        return find(self.window, control_type="CheckBox", name="paid", timeout=20)

    def _payment_combo(self):
        """The unnamed dropdown sitting beside the paid checkbox.

        Anchored on the checkbox rather than on a label because it has no label: the
        control to its left is the word "paid", which belongs to the checkbox.
        """
        return self._combo_on_row_with(self._paid_checkbox())

