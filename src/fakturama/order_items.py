"""The Order's Items grid: setting quantity and discount on a line.

    STATUS: written, not yet verified against the application. Everything else in
    src/fakturama has been run against Fakturama; this has not. Treat the cell
    navigation below as a hypothesis.

The grid has no UIA representation at all: no Table, no rows, no cells, nothing. Products
reach it by being selected in the product dialog, which works. Editing the values it then
shows is the part with no property-based route.

The approach here is the one that worked for the selector dialogs, which have the same
problem: click a row to give the grid focus and a current cell, then move with the
keyboard rather than computing a coordinate per cell. Only the row's vertical position is
derived from geometry; the column is reached by tabbing, so column widths and the fact
that some columns are hidden at narrow widths do not matter.

What is not yet known, and what a probe should establish first:

- Whether a single click on a cell starts editing it, or whether it needs a second click
  or F2. SWT grids differ.
- Whether Tab moves between cells within a row or jumps out of the grid entirely.
- The column order when the editor is maximized. Narrow, it shows Pos., Qty., Name, VAT,
  U.Price, Price and hides Discount; maximized it showed Pos., Qty., Item No., Picture,
  Name, Description, VAT, U.Price, Discount, Price. The Picture column may not be
  focusable, which would shift every count after it.
"""

import time

from src.errors import ManualReviewRequired
from src.models import LineItem
from src.uia import actions
from src.uia.locator import find

# Column order with the editor maximized, from the tree dump of an empty Order. Counted
# from Pos. at zero. Verify before relying on it: if Picture cannot take focus, the
# indices after it are wrong.
COLUMNS = ["Pos.", "Qty.", "Item No.", "Picture", "Name", "Description", "VAT",
           "U.Price", "Discount", "Price"]


class OrderItems:
    def __init__(self, main_window):
        self.main = main_window
        self.window = main_window.window

    def complete_line(self, row_index: int, item: LineItem) -> None:
        """Set the quantity and discount the source document gives for a line.

        U.Price and VAT are not set: they arrive correctly from the Product master when
        the product is selected, and the brief only asks that they be confirmed.
        """
        self.main.maximize_editor_area()
        try:
            self.set_cell(row_index, "Qty.", f"{item.quantity.normalize():f}")
            if item.discount_percent:
                self.set_cell(row_index, "Discount",
                              f"{item.discount_percent.normalize():f}")
        finally:
            self.main.restore_editor_area()

    def set_cell(self, row_index: int, column: str, value: str) -> None:
        """Put a value in one cell, reached by keyboard from the row's first cell."""
        if column not in COLUMNS:
            raise ManualReviewRequired(f"unknown Items column {column!r}",
                                       stage="items")

        self._click_row(row_index)
        self.window.type_keys("{TAB}" * COLUMNS.index(column), pause=0.15)
        time.sleep(0.3)

        # F2 first: SWT grids usually need the cell put into edit mode before typing,
        # and typing into a non-editing cell is silently discarded.
        self.window.type_keys("{F2}")
        time.sleep(0.3)
        self.window.type_keys("^a{DEL}", pause=0.05)
        self.window.type_keys(str(value), pause=0.08)
        self.window.type_keys("{ENTER}")
        time.sleep(0.8)

    def _click_row(self, row_index: int) -> None:
        """Click the first cell of a row, to focus the grid and set the current cell."""
        left, top = self._grid_origin()
        row_height = self._row_height()
        window = self.window.rectangle()

        x = left + 30
        y = top + row_height + int((row_index + 0.5) * row_height)
        self.window.click_input(coords=(x - window.left, y - window.top))
        actions.park_pointer()
        time.sleep(0.4)

    def _grid_origin(self) -> tuple[int, int]:
        """Top-left of the grid, taken from the Items label that heads it."""
        label = find(self.window, control_type="Text", name="Items", timeout=20)
        rect = label.rectangle()
        return (rect.right + 12, rect.top)

    def _row_height(self) -> int:
        from src.uia.actions import display_scale

        # Same logical row height as the selector grids, which look identical.
        return max(int(28 * display_scale()), 24)
