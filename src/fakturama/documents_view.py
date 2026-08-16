"""Data > Documents, the application's own record of what it has saved.

This is where the brief has us confirm a saved Order and, later, the Invoice beside it.
It matters that the check happens here rather than in the editor: the editor shows what
was typed, this shows what was stored.

Another drawn grid, so the rows are read from a capture.
"""

import time

from src import vision
from src.uia.locator import find_all, wait_until

VIEW = "Documents"

# The view's create button is named after the document type its tree is showing.
CREATE_PREFIX = "Create: "

# As shown in the brief's figures 8 and 10.
COLUMNS = ["Document", "Date", "Name", "Cust.Ref.", "State", "Total", "Printed"]


class DocumentsView:
    def __init__(self, main_window):
        self.main = main_window
        self.window = main_window.window

    def open(self) -> None:
        # This view lives in the bottom panel, and a maximized editor stack hides that
        # panel completely. Several steps maximize the editor and restore it afterwards,
        # but Eclipse persists the workbench layout across restarts, so a run that died
        # while maximized would otherwise leave the next run unable to open this view.
        self.main.restore_editor_area()

        self.main.open_navigation(VIEW)
        # The view builds in the bottom panel and is slow under emulation, so wait on its
        # own toolbar button rather than on a fixed time.
        self._create_button(timeout=45)
        time.sleep(1)

    def _create_button(self, timeout: float = 10.0):
        """The view's own "create a document" button, whatever it currently offers.

        Its name follows the document type selected in the view's tree: "Create: Order"
        while Orders are showing and "Create: Invoice" once an Invoice has been made,
        and the selection persists between runs. Anchoring on one type therefore works
        until the flow succeeds once, and then stops working, which is a memorable way
        to spend two runs. Matched on the prefix instead, excluding the main toolbar's
        "Create: New ..." buttons, which are a different set.
        """
        def look():
            for button in find_all(self.window, control_type="Button"):
                name = (button.element_info.name or "").strip()
                if name.startswith(CREATE_PREFIX) and "New" not in name:
                    return button
            return None

        return wait_until(look, timeout=timeout,
                          description="the Documents view's toolbar")

    def rows(self, save_to: str | None = None) -> list[dict]:
        """Every document currently listed."""
        try:
            anchor = self._create_button()
        except Exception:
            anchor = None
        window = self.window.rectangle()
        top = anchor.rectangle().bottom + 4 if anchor is not None \
            else window.top + window.height() // 2

        box = (window.left + 8, top, window.right - 8, window.bottom - 8)
        return vision.read_table(vision.capture_region(box, save_to), COLUMNS,
                                 what="the Documents list")

    def find_row(self, reference: str, save_to: str | None = None) -> dict | None:
        """The first row whose Cust.Ref. matches, or None.

        Only safe where the reference is known to be unique. It is not unique across
        repeated runs of the same document, so `find_document` is what the flow uses.
        """
        from src.matching import cell_matches

        for row in self.rows(save_to):
            if cell_matches(row.get("Cust.Ref.", ""), reference):
                return row
        return None

    def find_document(self, number: str, save_to: str | None = None) -> dict | None:
        """The row for one specific document, by the number Fakturama gave it.

        The number is read off the editor before saving rather than predicted, which is
        what makes this exact. Matching on Cust.Ref. instead looks fine until the same
        document is run twice: the list then holds two Orders carrying the same
        reference, the first one wins, and everything downstream is working on the
        previous run's document. That presented as the Invoice stage being unable to find
        an editor tab that was plainly on screen, because it had been told the Order was
        PO000001 while the tab in front of it said PO000002.
        """
        from src.matching import cell_matches

        for row in self.rows(save_to):
            if cell_matches(row.get("Document", ""), number):
                return row
        return None
