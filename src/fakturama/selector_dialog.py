"""The selector dialogs opened from an Order: "Select the address" and "Select a product".

They are the same widget with a different title and different columns, so the awkward
parts live here once. Those parts are:

- the results grid is drawn by the application and invisible to UIA, so rows are read
  from a screen capture rather than from the tree
- OK reports itself enabled whether or not a row is selected, so clicking it commits
  nothing while looking like success. Rows are committed with their default action
  instead
- the search box filters as you type and empties when focus leaves it, so it must not be
  tab-committed

This is shared because it is one widget. The resolve-or-create flows built on top of it
stay separate per entity, because those differ in every meaningful way.
"""

import time

from src import vision
from src.errors import ManualReviewRequired
from src.uia import actions, session
from src.uia.locator import find, labelled, wait_stable


class SelectorDialog:
    TITLE = ""
    COLUMNS: list[str] = []

    def __init__(self, window=None, timeout: float = 30.0):
        self.window = window or session.find_dialog(self.TITLE, timeout=timeout)

    @classmethod
    def is_open(cls, timeout: float = 2.0) -> bool:
        try:
            session.find_dialog(cls.TITLE, timeout=timeout)
            return True
        except Exception:
            return False

    # --- reading --------------------------------------------------------------

    def search(self, term: str) -> None:
        """Type into the search box and let the grid settle.

        The list filters as you type, so reading it too early gets a half-filtered
        result. Waiting for the picture to stop changing is what the brief means by
        waiting for the list to stabilize.
        """
        actions.set_text(labelled(self.window, "Search:"), term, commit=False,
                         what=f"{self.TITLE} search")
        wait_stable(lambda: len(vision.capture_region(self._grid_box())), settle=3)

    def rows(self, save_to: str | None = None) -> list[dict]:
        image = vision.capture_region(self._grid_box(), save_to)
        return vision.read_table(image, self.COLUMNS, what=self.TITLE)

    # --- choosing -------------------------------------------------------------

    def choose(self, row_index: int, close_timeout: float = 12.0) -> None:
        """Select a row and commit it, leaving the dialog closed.

        The wait for the dialog to disappear is generous on purpose. Committing is not
        instant, and double-clicking a dialog that is already closing throws inside
        Fakturama: it logs "Internal Error in: com.sebulli.fakturama.dialogs.Sele..."
        and, worse, abandons the commit, so the Order gains no line while the automation
        believes a product was chosen. Only fall back once it is genuinely still open.
        """
        self.select(row_index)

        self.window.type_keys("{ENTER}")
        if self._closed_within(close_timeout):
            return

        left, top, right, bottom = self._grid_box()
        window = self.window.rectangle()
        row_height = self._row_height()
        y = top + row_height + int((row_index + 0.5) * row_height)
        self.window.double_click_input(coords=(left + 200 - window.left,
                                               y - window.top))

        if not self._closed_within(close_timeout):
            raise ManualReviewRequired(
                f"{self.TITLE} would not close after selecting row {row_index}",
                stage="selector",
            )

    def _closed_within(self, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not self.is_open(timeout=0.5):
                # It has gone; give the editor behind it a moment to take the value.
                time.sleep(1.5)
                return True
            time.sleep(0.5)
        return False

    def select(self, row_index: int) -> None:
        """Move the selection to a row without committing it.

        Keyboard, not a computed click: the grid is invisible to UIA so its row height
        can only be guessed, and a wrong guess selects nothing while still letting the
        dialog close.
        """
        left, top, right, bottom = self._grid_box()
        window = self.window.rectangle()

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

    # --- internals ------------------------------------------------------------

    def _grid_box(self) -> tuple[int, int, int, int]:
        """The results grid: everything between the search row and the buttons.

        Derived from live control positions rather than written down, so it follows the
        dialog when it moves or resizes.
        """
        dialog = self.window.rectangle()
        search = labelled(self.window, "Search:").rectangle()
        ok = find(self.window, control_type="Button", name="OK").rectangle()
        return (dialog.left + 4, search.bottom + 4, dialog.right - 4, ok.top - 8)

    # A grid row in these dialogs is about 28 logical pixels tall. Kept in logical units
    # and scaled at run time, so it holds on any display scaling. The search box is a
    # poor proxy for this: it is a single-line control roughly two thirds the height of a
    # grid row, and using it put the click on the header rather than the first row.
    ROW_HEIGHT_LOGICAL = 28

    def _row_height(self) -> int:
        from src.uia.actions import display_scale

        return max(int(self.ROW_HEIGHT_LOGICAL * display_scale()), 24)
