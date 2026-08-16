"""The Order's Items grid: setting quantity and discount on a line.

The grid has no UIA representation at all, so this is the one place the automation
drives a widget the way a person does. Three things make that safe enough:

1. **The row is never searched for.** The brief's own sequence is select a product,
   then complete that line, and Fakturama leaves the freshly added row highlighted.
   The highlight is a saturated blue band, found by plain pixel counting, no model.
2. **Columns are grounded from their headers at run time.** The header strip is crisp
   rendered text, so the vision model is asked once where "Qty." and "Discount" sit,
   and cell x-centres come from that answer. Nothing is hardcoded.
3. **Every write is read back from the grid itself** through the existing table
   reader, compared numerically, and retried with a different activation (double-click,
   then F2) before stopping for manual review. Behind all of it sits the stage 4
   totals gate, so a wrong value cannot reach a saved document.

STATUS, verified against the live application: the highlighted row is found, the cell
click is aimed by grounding the cell's own text, and the read-back identifies the row by
Pos. and reports its true value. What does not yet work is activating the cell editor:
both double-click and F2 leave the value unchanged, the read-back says so, and the flow
stops for manual review with the capture saved as evidence. That activation step is the
single remaining gap in stage 3.
"""

import time

from src import vision
from src.errors import ManualReviewRequired
from src.models import LineItem
from src.uia import actions
from src.uia.actions import _as_number
from src.uia.locator import find

# Column headers when the editor is maximized. Only the ones we edit are grounded;
# the full list is what the read-back passes to the table reader.
# What the grid actually shows, from a saved read-back capture. There is no Item No.
# column, so rows are identified by Pos., which we control by adding lines in source
# order and which typing accidents cannot corrupt.
COLUMNS = ["Pos.", "Qty.", "Name", "VAT", "U.Price", "Price"]

GRID_HEIGHT = 420  # captured depth below the header; ~8 rows, plenty for this order


class OrderItems:
    def __init__(self, main_window):
        self.main = main_window
        self.window = main_window.window

    def complete_current_line(self, item: LineItem, log=print) -> None:
        """Set quantity and discount on the row the selector just added.

        Called immediately after the product dialog commits, while its row is still
        highlighted. The row's position is captured once here and reused for both
        cells, because committing a cell can move the selection.
        """
        grid = self._grid_box()
        row_y = self._highlighted_row_y(grid)
        log(f"  completing the line at y={row_y}")

        quantity = f"{item.quantity.normalize():f}"
        self._set_cell(grid, row_y, "Qty.", quantity, item.quantity, item, log)

        if item.discount_percent:
            discount = f"{item.discount_percent.normalize():f}"
            self._set_cell(grid, row_y, "Discount", discount,
                           item.discount_percent, item, log)

    # --- one cell -------------------------------------------------------------

    def _set_cell(self, grid, row_y: int, column: str, text: str,
                  expected, item: LineItem, log) -> None:
        if column == "Qty.":
            # Aim at the quantity value itself rather than under its header: the
            # header box grounds loosely and a click a column over lands in Name,
            # which is exactly what happened. The fresh line always reads 1.00.
            x = self._ground_in_row(grid, row_y, "1.00")
        else:
            x = self._column_center(grid, column)
        window = self.window.rectangle()
        point = (x - window.left, row_y - window.top)

        for activation in ("double-click", "f2"):
            if activation == "double-click":
                self.window.double_click_input(coords=point)
            else:
                self.window.click_input(coords=point)
                time.sleep(0.3)
                self.window.type_keys("{F2}")
            actions.park_pointer()
            time.sleep(0.6)

            self.window.type_keys("^a{DEL}", pause=0.05)
            self.window.type_keys(text, pause=0.08)
            self.window.type_keys("{ENTER}")
            time.sleep(1.0)

            shown = self._read_cell(grid, item, column)
            value = _as_number(shown or "")
            # Fakturama displays a discount as "-10.00 %", so compare magnitudes.
            if value is not None and abs(value) == abs(expected):
                log(f"  {column} = {shown!r}")
                return
            log(f"  {column} via {activation}: shows {shown!r}, wanted {text}")

        raise ManualReviewRequired(
            f"could not set {column} to {text!r} on the line for {item.sku!r}",
            stage="items",
        )

    # --- geometry, all derived at run time -------------------------------------

    def _grid_box(self) -> tuple[int, int, int, int]:
        label = find(self.window, control_type="Text", name="Items", timeout=20)
        rect = label.rectangle()
        window = self.window.rectangle()
        return (rect.right + 8, rect.top, window.right - 40,
                rect.top + GRID_HEIGHT)

    def _highlighted_row_y(self, grid) -> int:
        capture = vision.capture_region(grid)
        centre = vision.selection_row_center(capture)
        if centre is None:
            raise ManualReviewRequired(
                "no highlighted row in the Items grid; expected the freshly added "
                "line to still be selected",
                stage="items",
            )
        return grid[1] + centre

    def _column_center(self, grid, column: str) -> int:
        centres = getattr(self.main, "_items_column_centers", None)
        if centres is None:
            header = (grid[0], grid[1], grid[2], grid[1] + 60)
            boxes = vision.ground_boxes(
                vision.capture_region(header), ["Qty.", "Discount"],
                what="the Items grid header",
            )
            centres = {
                label: grid[0] + (box[0] + box[2]) // 2
                for label, box in boxes.items()
            }
            self.main._items_column_centers = centres

        if column not in centres:
            raise ManualReviewRequired(
                f"the {column!r} header was not found in the Items grid; "
                f"found {sorted(centres)}",
                stage="items",
            )
        return centres[column]

    def _ground_in_row(self, grid, row_y: int, text: str) -> int:
        strip = (grid[0], row_y - 30, grid[2], row_y + 30)
        boxes = vision.ground_boxes(vision.capture_region(strip), [text],
                                    what="the item row")
        if text not in boxes:
            raise ManualReviewRequired(
                f"could not locate {text!r} in the item row", stage="items")
        x1, _, x2, _ = boxes[text]
        return strip[0] + (x1 + x2) // 2

    def _read_cell(self, grid, item: LineItem, column: str) -> str | None:
        rows = vision.read_table(
            vision.capture_region(grid, save_to="runs/items-readback.png"),
            COLUMNS, what="the Items grid")
        for row in rows:
            if (row.get("Pos.", "") or "").strip() == str(item.position):
                return row.get(column)
        return None
