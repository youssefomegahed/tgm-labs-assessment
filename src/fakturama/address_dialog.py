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

    def choose(self, row_index: int) -> None:
        """Select a row and commit it, leaving the dialog closed.

        Selecting and clicking OK does not work. OK reports itself enabled whether or
        not a row is selected, so the click succeeds, the dialog closes and the Order is
        left with no address, which reads exactly like a successful selection. This dialog
        wants the row's default action instead: Enter, or a double click.

        Row choice stays on the keyboard so it is exact; only the commit is a gesture.
        """
        self.select(row_index)

        self.window.type_keys("{ENTER}")
        time.sleep(1.5)
        if not self.is_open(timeout=2):
            return

        # Enter did not take, so use the row's other default action. The y here is
        # derived from the live grid rather than written down: one header's height in,
        # plus the wanted row.
        left, top, right, bottom = self._grid_box()
        window = self.window.rectangle()
        row_height = self._row_height()
        y = top + row_height + int((row_index + 0.5) * row_height)
        self.window.double_click_input(coords=(left + 200 - window.left,
                                               y - window.top))
        time.sleep(1.5)

    def _row_height(self) -> int:
        """Height of one grid row, taken from the search box rather than guessed.

        Both are single-line controls laid out by the same widget toolkit at the same
        font size, so the search box is a good proxy and it scales with the display,
        which a hardcoded pixel count does not.
        """
        return max(labelled(self.window, "Search:").rectangle().height(), 24)

    def select(self, row_index: int) -> None:
        """Select a row by its position in what rows() returned.

        Navigated by keyboard rather than by clicking a computed y coordinate. The grid
        is invisible to UIA, so its row height can only be guessed, and a guess that is
        wrong selects nothing while still letting OK close the dialog. The flow then
        carries on believing it picked a customer it never picked.

        One click puts focus in the grid, Home takes it to the first row whichever row
        that click happened to land on, and Down steps to the wanted one.
        """
        left, top, right, bottom = self._grid_box()
        window = self.window.rectangle()

        # Anywhere in the grid body will do: the click is only for focus, and the
        # keyboard decides which row ends up selected.
        self.window.click_input(coords=(left + 120 - window.left,
                                        top + (bottom - top) // 2 - window.top))
        time.sleep(0.4)

        self.window.type_keys("{HOME}")
        time.sleep(0.3)
        if row_index:
            self.window.type_keys("{DOWN}" * row_index)
            time.sleep(0.3)

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
