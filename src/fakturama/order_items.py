"""The Order's Items grid: completing a line after its Product has been selected.

The grid is drawn rather than built from widgets, so the tree holds one empty Pane where
the rows should be. That made line entry look like the one place with no property-based
route at all. It is not, and the distinction that matters took a diagnostic to find:

**the grid is drawn, but its cell editor is a real widget.** Double-clicking a cell adds
an `Edit` to the UIA tree, sized and positioned exactly over that cell, and a combo's
list beside it. So the value goes in through the same value pattern as every other field
in this project, and can be read back the same way. Only *aiming* the double-click has
to be solved by looking at pixels.

Aiming is where the first attempt went wrong, and the failure is worth recording because
it was silent. Column positions were grounded by asking a vision model where "Qty." sat.
On a normally proportioned screenshot that works. On this one, a header strip around
2300x60, the returned boxes came back roughly twice too far right, so the double-click
landed in the VAT column, the quantity was typed into a VAT dropdown, and Fakturama
discarded it without complaint. `vision.column_edges` replaces that with plain pixel
work: SWT paints the headers in a flat colour and leaves the dividers unpainted, so a
divider is a narrow gap in that colour. No model, no API call, and the same answer every
time.

Two independent sources still have to agree before anything is written. Position comes
from those pixels; column *names* come from the table read-back, which the model does
well because it is reading text rather than measuring. A cell is only written to when
the editor that opened holds the value the read-back attributes to that column.
"""

import time

from src import vision
from src.errors import ManualReviewRequired
from src.models import LineItem
from src.uia import actions
from src.uia.actions import _as_number
from src.uia.locator import find, iter_descendants

# The grid as a default Fakturama 2.2.0 shows it. "Pos." is a row header rather than a
# data column, so it is excluded from the positional mapping below; it still names rows
# in the read-back, which is how a line is identified after the fact.
ROW_HEADER = "Pos."
DATA_COLUMNS = ["Qty.", "Name", "VAT", "U.Price", "Price"]
COLUMNS = [ROW_HEADER] + DATA_COLUMNS

GRID_HEIGHT = 420  # captured depth below the header; ~8 rows, plenty for this order

STAGE = "items"


class OrderItems:
    def __init__(self, main_window):
        self.main = main_window
        self.window = main_window.window

    def complete_current_line(self, item: LineItem, log=print) -> None:
        """Set quantity and discount on the row the selector just added.

        Called while that row is still highlighted, which is what identifies it: the
        brief's own sequence is select a product then complete its line, and Fakturama
        leaves the freshly added row selected. The row's position is read once and reused
        for both cells, because committing one can move the selection.
        """
        grid = self._grid_box()
        row_y = self._highlighted_row_y(grid)
        spans = self._column_spans(grid)
        log(f"  line at y={row_y}, columns {sorted(spans)}")

        self._set_cell(grid, spans, row_y, "Qty.", item.quantity, item, log)

        if item.discount_percent:
            if "Discount" not in spans:
                raise ManualReviewRequired(
                    f"line {item.position} carries a {item.discount_percent}% discount "
                    f"and this Order's item grid has no Discount column, so there is "
                    f"nowhere to put it. Columns present: {', '.join(DATA_COLUMNS)}.",
                    stage=STAGE,
                )
            self._set_cell(grid, spans, row_y, "Discount", item.discount_percent,
                           item, log)

        self._confirm_line(grid, item, log)

    # --- one cell -------------------------------------------------------------

    def _set_cell(self, grid, spans, row_y: int, column: str, expected,
                  item: LineItem, log) -> None:
        """Open a cell's editor, check it is the cell we meant, write, and verify."""
        text = f"{expected.normalize():f}"

        for attempt in range(2):
            cell = self._open_editor(grid, spans, row_y, column, item, log)

            try:
                cell.set_edit_text(text)
            except Exception:
                # Some SWT editors ignore the value pattern without raising. Real
                # keystrokes are indistinguishable to the widget from a person typing,
                # and focus is already in the editor, so they need no click.
                from pywinauto import keyboard

                keyboard.send_keys("^a", pause=0.1)
                keyboard.send_keys(text, pause=0.12)

            # Enter rather than Tab: Tab commits and moves the editor to the next cell,
            # which would leave an editor open over the row we are about to re-read.
            from pywinauto import keyboard

            keyboard.send_keys("{ENTER}")
            time.sleep(1.2)
            actions.park_pointer()

            shown = self._read_cell(grid, item, column)
            value = _as_number(shown or "")
            # Fakturama displays a discount as "-10.00 %", so compare magnitudes.
            if value is not None and abs(value) == abs(expected):
                log(f"  {column} = {shown!r}")
                return
            log(f"  {column} attempt {attempt + 1}: shows {shown!r}, wanted {text}")

        raise ManualReviewRequired(
            f"could not set {column} to {text!r} on the line for {item.sku!r}",
            stage=STAGE,
        )

    def _open_editor(self, grid, spans, row_y: int, column: str,
                     item: LineItem, log):
        """Double-click a cell and hand back the editor widget that appears.

        The editor is only accepted once it has been shown to be the right one, by two
        checks that fail in different ways. Its rectangle has to sit inside the column
        the pixels identified, which catches an aim that drifted. And the value it opens
        holding has to be the value the table read-back attributes to that column on this
        row, which catches the columns being in an order we did not expect. The first
        attempt at this file had neither check, and typed quantities into a VAT dropdown
        for three runs without ever reporting a problem.
        """
        left, right = spans[column]
        point = (left + (right - left) // 2, row_y)

        before = {rect for rect, _ in self._editors(grid)}

        from pywinauto import mouse

        mouse.double_click(coords=point)
        time.sleep(1.0)

        fresh = [(rect, element) for rect, element in self._editors(grid)
                 if rect not in before]
        if not fresh:
            raise ManualReviewRequired(
                f"double-clicking the {column} cell of line {item.position} at {point} "
                f"opened no editor",
                stage=STAGE,
            )

        rect, cell = fresh[0]
        centre = (rect[0] + rect[2]) // 2
        if not left <= centre <= right:
            raise ManualReviewRequired(
                f"the editor for {column} opened at x={centre}, outside that column's "
                f"{left}..{right}; the grid is not laid out as expected",
                stage=STAGE,
            )

        opened_with = actions.read_value(cell)
        listed = self._read_cell(grid, item, column)
        if listed is not None and not _same_cell(opened_with, listed):
            raise ManualReviewRequired(
                f"opened the cell at the {column} position and it holds "
                f"{opened_with!r}, but the grid lists {listed!r} for {column} on line "
                f"{item.position}; refusing to write to a cell I cannot identify",
                stage=STAGE,
            )
        log(f"  {column} editor open holding {opened_with!r}")
        return cell

    def _editors(self, grid) -> list:
        """Every Edit currently sitting inside the grid, as (rect, element).

        Cell editors are transient, so this is called either side of a click and the
        difference is the editor that just opened.
        """
        found = []
        for element in iter_descendants(self.window):
            try:
                if element.element_info.control_type != "Edit":
                    continue
                rect = element.rectangle()
            except Exception:
                continue
            if grid[0] - 40 <= rect.left and rect.right <= grid[2] + 40 \
                    and grid[1] - 40 <= rect.top and rect.bottom <= grid[3] + 40:
                found.append(((rect.left, rect.top, rect.right, rect.bottom), element))
        return found

    # --- geometry, all derived at run time -------------------------------------

    def _grid_box(self) -> tuple[int, int, int, int]:
        label = find(self.window, control_type="Text", name="Items", timeout=20)
        rect = label.rectangle()
        window = self.window.rectangle()
        return (rect.right + 8, rect.top, window.right - 40, rect.top + GRID_HEIGHT)

    def _highlighted_row_y(self, grid) -> int:
        capture = vision.capture_region(grid)
        centre = vision.selection_row_center(capture)
        if centre is None:
            raise ManualReviewRequired(
                "no highlighted row in the Items grid; expected the freshly added "
                "line to still be selected",
                stage=STAGE,
            )
        return grid[1] + centre

    def _column_spans(self, grid) -> dict[str, tuple[int, int]]:
        """Each data column's screen x-span, keyed by name.

        The pixels give the dividers; the names come from `DATA_COLUMNS` in order. That
        mapping is only safe while the two agree on how many columns there are, so a
        mismatch stops the run rather than guessing. It is also the check that would
        notice a Fakturama configured to show the Discount column, which this one is not.
        """
        cached = getattr(self.main, "_items_column_spans", None)
        if cached is not None:
            return cached

        # `column_edges` answers in the capture's own coordinates, so the grid's left
        # edge has to be added back to get screen coordinates. Leaving it out put the
        # click at x=186 instead of x=862, which is off the grid entirely; the editor
        # check below is what turned that into a named failure rather than a stray click.
        edges = [grid[0] + edge
                 for edge in vision.column_edges(vision.capture_region(grid))]
        spans = [(edges[index], edges[index + 1]) for index in range(len(edges) - 1)]

        if len(spans) != len(DATA_COLUMNS):
            raise ManualReviewRequired(
                f"the Items grid has {len(spans)} data columns and this flow knows the "
                f"names of {len(DATA_COLUMNS)} ({', '.join(DATA_COLUMNS)}), so a column "
                f"cannot be identified by position",
                stage=STAGE,
            )

        found = dict(zip(DATA_COLUMNS, spans))
        self.main._items_column_spans = found
        return found

    # --- reading back ----------------------------------------------------------

    def _read_cell(self, grid, item: LineItem, column: str) -> str | None:
        for row in self._rows(grid):
            if (row.get(ROW_HEADER, "") or "").strip() == str(item.position):
                return row.get(column)
        return None

    def _rows(self, grid) -> list[dict]:
        return vision.read_table(
            vision.capture_region(grid, save_to="runs/items-readback.png"),
            COLUMNS, what="the Items grid")

    def _confirm_line(self, grid, item: LineItem, log) -> None:
        """The brief's steps 3.14 and 3.16, from a single read of the row.

        U.Price and the VAT rate are worth confirming even though this flow never types
        them: they come across from the Product master, and a Product that already
        existed under this SKU can carry a price that is not the one this order was
        written against. The line total alone would not tell that apart from a quantity
        error, and each of the three is a different way for the document to be wrong.

        One read for all three, because each one costs a model call.
        """
        row = next((candidate for candidate in self._rows(grid)
                    if (candidate.get(ROW_HEADER, "") or "").strip() == str(item.position)),
                   None)
        if row is None:
            raise ManualReviewRequired(
                f"line {item.position} ({item.sku}) is not in the Items grid to check",
                stage=STAGE,
            )

        wrong = []

        unit = _as_number(row.get("U.Price", ""))
        if unit is None or unit != item.unit_net:
            wrong.append(f"U.Price shows {row.get('U.Price')!r}, document says "
                         f"{item.unit_net}")

        # The cell is clipped to something like "VAT 19% (19.0...", so the rate's name is
        # the part of it that identifies the rate.
        vat = (row.get("VAT") or "").strip()
        if not vat.startswith(item.vat_rate_name):
            wrong.append(f"VAT shows {vat!r}, expected the rate "
                         f"{item.vat_rate_name!r}")

        total = _as_number(row.get("Price", ""))
        if total is None or total != item.line_net:
            wrong.append(f"the line total shows {row.get('Price')!r}, document says "
                         f"{item.line_net}")

        if wrong:
            raise ManualReviewRequired(
                f"line {item.position} ({item.sku}) does not match the document:\n  "
                + "\n  ".join(wrong),
                stage=STAGE,
            )
        log(f"  U.Price {row.get('U.Price')!r}, VAT {vat!r}, "
            f"total {row.get('Price')!r}, all as the document")


def _same_cell(opened: str, listed: str) -> bool:
    """Is the editor holding what the grid lists for this cell?

    Compared loosely on purpose. An editor opens holding an unformatted value where the
    grid shows a formatted one: "250" against "$250.00", "1" against "1.00". Numbers are
    therefore compared by meaning, and text only has to be a prefix, because the grid
    clips a long name to "Ergonomic Des..." while the editor holds all of it.
    """
    opened, listed = (opened or "").strip(), (listed or "").strip()
    if not opened or not listed:
        return True  # nothing to disagree about; the positional checks still stand

    opened_number, listed_number = _as_number(opened), _as_number(listed)
    if opened_number is not None and listed_number is not None:
        return opened_number == listed_number

    trimmed = listed.rstrip(".…")
    return opened.startswith(trimmed) or listed.startswith(opened)
