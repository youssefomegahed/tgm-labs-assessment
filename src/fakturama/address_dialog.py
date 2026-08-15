"""The "Select the address" dialog, opened from the Order.

This is the brief's existence check for a Debtor. It is also the one place where UIA
runs out: the results grid is drawn by the application and the tree holds a single empty
Pane where the rows should be. The Search box, OK and Cancel are all reachable normally;
the rows are read from a screenshot.
"""

import time

from src import vision
from src.uia import actions, session
from src.uia.locator import find, labelled, wait_stable

TITLE = "Select the address"

# The columns the brief names as deciding an exact match, in the order they appear.
COLUMNS = ["No.", "First Name", "Name", "Company", "ZIP", "City"]


class AddressDialog:
    def __init__(self, window=None, timeout: float = 30.0):
        self.window = window or session.find_dialog(TITLE, timeout=timeout)

    @classmethod
    def is_open(cls, timeout: float = 2.0) -> bool:
        try:
            session.find_dialog(TITLE, timeout=timeout)
            return True
        except Exception:
            return False

    def search(self, term: str) -> None:
        """Type into the search box and let the grid settle.

        The list filters as you type, so reading it too early gets a half-filtered
        result. wait_stable is what the brief means by waiting for the list to
        stabilize: keep looking until the picture stops changing.
        """
        actions.set_text(labelled(self.window, "Search:"), term, what="address search")
        wait_stable(lambda: len(vision.capture_region(self._grid_box())), settle=3)

    def rows(self, save_to: str | None = None) -> list[dict]:
        """Every visible result row, as dicts keyed by column name."""
        image = vision.capture_region(self._grid_box(), save_to)
        return vision.read_table(image, COLUMNS, what="the address selector")

    def select(self, row_index: int) -> None:
        """Click a row by its position in what rows() returned."""
        left, top, right, bottom = self._grid_box()
        header, row_height = 34, 34  # measured off the live grid below
        y = top + header + int((row_index + 0.5) * row_height)
        self.window.click_input(coords=(left + 120 - self.window.rectangle().left,
                                        y - self.window.rectangle().top))
        time.sleep(0.4)

    def ok(self) -> None:
        actions.click(find(self.window, control_type="Button", name="OK"))

    def cancel(self) -> None:
        actions.click(find(self.window, control_type="Button", name="Cancel"))

    # --- internals -----------------------------------------------------------

    def _grid_box(self) -> tuple[int, int, int, int]:
        """The results grid: everything between the search row and the buttons.

        Derived from live control positions rather than written down, so it follows the
        dialog when it moves or resizes.
        """
        dialog = self.window.rectangle()
        search = labelled(self.window, "Search:").rectangle()
        ok = find(self.window, control_type="Button", name="OK").rectangle()

        return (dialog.left + 4, search.bottom + 4, dialog.right - 4, ok.top - 8)
