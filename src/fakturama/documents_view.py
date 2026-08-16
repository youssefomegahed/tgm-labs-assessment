"""Data > Documents, the application's own record of what it has saved.

This is where the brief has us confirm a saved Order and, later, the Invoice beside it.
It matters that the check happens here rather than in the editor: the editor shows what
was typed, this shows what was stored.

Another drawn grid, so the rows are read from a capture.
"""

import time

from src import vision
from src.uia.locator import find, find_optional

VIEW = "Documents"

# As shown in the brief's figures 8 and 10.
COLUMNS = ["Document", "Date", "Name", "Cust.Ref.", "State", "Total", "Printed"]


class DocumentsView:
    def __init__(self, main_window):
        self.main = main_window
        self.window = main_window.window

    def open(self) -> None:
        self.main.open_navigation(VIEW)
        # The view builds in the bottom panel and is slow under emulation. Wait for its
        # own toolbar button rather than for a fixed time.
        find(self.window, control_type="Button", contains="Create: Order", timeout=45)
        time.sleep(1)

    def rows(self, save_to: str | None = None) -> list[dict]:
        """Every document currently listed."""
        anchor = find_optional(self.window, control_type="Button",
                               contains="Create: Order", timeout=10)
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
