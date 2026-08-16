"""The selector dialogs opened from an Order: "Select the address" and "Select a product".

Driven without UIA, deliberately. These modals are the one surface where UIA traversal
intermittently wedges Fakturama's whole UI thread under emulation: win32 sees the window,
every UIA query times out, and input queued during the wedge replays when the automation
process dies, so selections appear to happen on their own. Three separate sessions died
to three different symptoms of that one cause.

So this class speaks only win32, screenshots, the vision grounder and the raw keyboard:

- the window comes from EnumWindows and its geometry from GetWindowRect
- the search box is grounded from the "Search:" label on a capture, once per open
- rows are read from captures, as they always were, the grid being drawn anyway
- a row is chosen by clicking it and committing with Enter; Escape cancels; WM_CLOSE
  is the last resort, being what the title-bar X sends

Every coordinate is derived from the live window on the current run.
"""

import time

from src import vision
from src.errors import ManualReviewRequired
from src.uia import session


class SelectorClosedEarly(Exception):
    """The dialog vanished before we finished with it.

    Not necessarily a failure: the product selector commits itself when the search
    narrows to a single exact match, taking the row with it. The caller decides by
    checking whether the Order actually gained a line.
    """


class SelectorDialog:
    TITLE = ""
    COLUMNS: list[str] = []

    # A change taller than this fraction of the grid is a re-sort repainting every row
    # rather than one row being selected. A row is a small part of a grid several
    # hundred pixels tall, so there is a lot of daylight between the two.
    RESORT_FRACTION = 0.30

    def __init__(self, timeout: float = 30.0):
        self.handle = session.find_dialog_handle(self.TITLE, timeout=timeout)
        time.sleep(1.5)  # let the dialog finish building before we look at it
        self._search_box: tuple[int, int, int, int] | None = None

    # --- win32 basics ---------------------------------------------------------

    @classmethod
    def is_open(cls, timeout: float = 2.0) -> bool:
        deadline = time.monotonic() + timeout
        while True:
            if session.dialog_exists(cls.TITLE):
                return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.3)

    def rect(self) -> tuple[int, int, int, int]:
        import win32gui

        try:
            return win32gui.GetWindowRect(self.handle)
        except Exception as exc:
            raise SelectorClosedEarly(f"{self.TITLE} is no longer open") from exc

    # --- searching ------------------------------------------------------------

    def search(self, term: str) -> None:
        """Click into the search box, type the term, let the grid settle."""
        from pywinauto import keyboard, mouse

        label = self._find_search_label()
        # The input sits immediately right of the label and is a few hundred px wide.
        x = label[2] + 60
        y = (label[1] + label[3]) // 2

        mouse.click(coords=(x, y))
        time.sleep(0.5)
        keyboard.send_keys("^a{BACKSPACE}", pause=0.05)
        keyboard.send_keys(term, with_spaces=True, pause=0.05)

        from src.uia.locator import wait_stable

        wait_stable(lambda: len(vision.capture_region(self._grid_box())), settle=3)

    def rows(self, save_to: str | None = None) -> list[dict]:
        image = vision.capture_region(self._grid_box(), save_to)
        return vision.read_table(image, self.COLUMNS, what=self.TITLE)

    # --- choosing and leaving -------------------------------------------------

    def choose(self, row_index: int, close_timeout: float = 12.0) -> None:
        """Select a row and commit it, leaving the dialog closed.

        The click is verified, not assumed. Row geometry derived from the grounded
        label jitters a few pixels between runs, and a click that lands on empty grid
        selects nothing while looking identical from outside. So after each candidate
        click the grid is captured and the local pixel detector confirms a highlight
        exists before anything is committed. Once any row is selected, Home and Down
        make the row choice exact regardless of which row the click hit.
        """
        from pywinauto import keyboard, mouse

        grid = self._grid_box()
        x = grid[0] + 200

        # Walk candidate heights until a click demonstrably changes one row.
        #
        # Two things a click here can do, and they have to be told apart. Landing on a
        # row selects it and repaints that row. Landing on a column header re-sorts the
        # list and repaints all of them, selecting nothing, after which Home and Enter
        # have nothing to act on and the dialog simply stays open. That was the
        # "would not close after choosing row 0" failure, and it took two runs in three.
        #
        # Height is what separates them, so the band's extent is measured rather than
        # just its centre. Colour is not usable: this dialog paints a selected row as a
        # pale wash with a dotted border, not the saturated blue the Items grid uses, and
        # a colour test sees nothing on a row that is plainly selected.
        rows_are_stale = False
        selected_centre = None
        for offset in (60, 45, 80, 95, 110, 130):
            before = vision.capture_region(grid)
            mouse.click(coords=(x, grid[1] + offset))
            time.sleep(0.5)
            band = vision.changed_row_band(before, vision.capture_region(grid))
            if band is None:
                continue
            if band[1] - band[0] > (grid[3] - grid[1]) * self.RESORT_FRACTION:
                rows_are_stale = True
                break
            selected_centre = (band[0] + band[1]) // 2
            break

        if rows_are_stale:
            # The caller matched a row by index against a list read before this click.
            # After a re-sort that index means something else, so there is nothing safe
            # left to do here.
            raise ManualReviewRequired(
                f"clicking in {self.TITLE} re-sorted the list instead of selecting a "
                f"row, so the row the search matched can no longer be identified",
                stage="selector")
        if selected_centre is None:
            raise ManualReviewRequired(
                f"could not select any row in {self.TITLE}", stage="selector"
            )

        # A selection exists, so Home reliably moves it to the first row.
        keyboard.send_keys("{HOME}")
        time.sleep(0.4)
        if row_index:
            keyboard.send_keys("{DOWN}" * row_index, pause=0.15)
            time.sleep(0.4)

        keyboard.send_keys("{ENTER}")
        if self._closed_within(close_timeout):
            return

        # Enter did not commit; double-click exactly where the selection landed.
        mouse.double_click(coords=(x, grid[1] + selected_centre))
        if self._closed_within(close_timeout):
            return

        raise ManualReviewRequired(
            f"{self.TITLE} would not close after choosing row {row_index}",
            stage="selector",
        )

    def cancel(self) -> None:
        """Escape first; WM_CLOSE if the dialog lingers. Never a click on OK."""
        from pywinauto import keyboard

        keyboard.send_keys("{ESC}")
        if self._closed_within(4.0):
            return

        import win32con
        import win32gui

        win32gui.PostMessage(self.handle, win32con.WM_CLOSE, 0, 0)
        self._closed_within(4.0)

    def _closed_within(self, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not session.dialog_exists(self.TITLE):
                time.sleep(1.5)  # give the editor behind it a moment to take the value
                return True
            time.sleep(0.5)
        return False

    # --- geometry, grounded on the live window ---------------------------------

    def _find_search_label(self) -> tuple[int, int, int, int]:
        """Where "Search:" is painted, in screen coordinates, grounded once per open."""
        if self._search_box is not None:
            return self._search_box

        left, top, right, bottom = self.rect()
        # The search row lives in the dialog's top strip.
        strip = (left, top, right, top + max(160, (bottom - top) // 6))
        boxes = vision.ground_boxes(vision.capture_region(strip), ["Search:"],
                                    what=f"the {self.TITLE} search row")
        if "Search:" not in boxes:
            raise ManualReviewRequired(
                f"could not locate the search box in {self.TITLE}",
                stage="selector",
            )
        x1, y1, x2, y2 = boxes["Search:"]
        self._search_box = (strip[0] + x1, strip[1] + y1, strip[0] + x2, strip[1] + y2)
        return self._search_box

    def _grid_box(self) -> tuple[int, int, int, int]:
        """The results grid: below the search row, above the button strip."""
        left, top, right, bottom = self.rect()
        label = self._find_search_label()
        return (left + 6, label[3] + 8, right - 6, bottom - 70)

    def _row_height(self) -> int:
        """A row is a single line of the same text the search label uses."""
        label = self._find_search_label()
        return max((label[3] - label[1]) * 2, 24)

    def _row_point(self, row_index: int) -> tuple[int, int]:
        """Middle of a data row: one header down from the grid top, then N rows."""
        left, top, right, bottom = self._grid_box()
        row_height = self._row_height()
        return (left + 200, top + row_height + int((row_index + 0.5) * row_height))
