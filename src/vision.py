"""Reading tables that Fakturama draws itself.

The address selector and the product selector show their results in a grid that UIA
cannot see at all: the tree has a single empty Pane where the rows should be, with no
Table, no rows and no cells. The columns the brief tells us to match on, Company, First
Name, Name, ZIP and City, simply are not available as data.

So we look at them. Screenshot the grid, hand it to a vision model with the column names
and a schema, and get rows back as dicts. matching.py already works on dicts of column
name to text, so nothing downstream has to know where the rows came from.

This is the fallback the design keeps for controls that are neither named nor
positionally ordered. It costs an API call and it is not free of risk, which is why the
brief's rule that ambiguity stops the flow matters more here than anywhere else.
"""

import io

from google.genai import types

from src.errors import ExtractionError
from src.gemini import generate_json

READ_TABLE_PROMPT = """\
This is a screenshot of a table from a desktop application.

Read every populated data row. Ignore the header row itself, and ignore rows that are \
blank filler below the data.

For each row, return one object with a key per column listed in the schema, holding the \
text shown in that column for that row, exactly as displayed.

Two things to be careful about:

- If a cell's text is clipped by the column width and ends in an ellipsis, include the \
ellipsis. Do not guess at the full value. Downstream code relies on knowing a value was \
clipped.
- If a cell is empty, return an empty string for it.

If the table has no data rows at all, return an empty list.
"""


def table_schema(columns: list[str]) -> dict:
    return {
        "type": "object",
        "properties": {
            "rows": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        column: {"type": "string", "description": f"the {column} column"}
                        for column in columns
                    },
                    "required": list(columns),
                },
            }
        },
        "required": ["rows"],
    }


def capture_region(box: tuple[int, int, int, int], save_to: str | None = None) -> bytes:
    """A PNG of a screen rectangle, as (left, top, right, bottom).

    Grabs the framebuffer rather than asking a control to paint itself: SWT draws
    through Java and PrintWindow comes back as a black rectangle.

    The rectangle is always computed from live control positions by the caller, never
    written down, so it follows the window around rather than breaking when it moves.
    """
    from PIL import ImageGrab

    # Clear anything that has appeared over the app since the run started. A new
    # console arrives with every remote command, and a covered region captures as the
    # console's body rather than the table.
    try:
        from src.uia.session import minimize_consoles

        minimize_consoles()
        # And get the pointer off whatever it is hovering: a tooltip left open over a
        # grid reads as part of the grid. Clicks are long finished by capture time, so
        # moving the pointer here cannot race a dialog opening, which it did when the
        # move happened right after the click.
        from src.uia.actions import park_pointer

        park_pointer()
        import time as _time

        _time.sleep(0.4)  # give the tooltip a beat to disappear
    except Exception:
        pass

    image = ImageGrab.grab(bbox=box, all_screens=True)
    if save_to:
        image.save(save_to)  # keeping the evidence for the run log

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def capture(element, save_to: str | None = None) -> bytes:
    rect = element.rectangle()
    return capture_region((rect.left, rect.top, rect.right, rect.bottom), save_to)


def looks_blank(image: bytes, tolerance: int = 8) -> bool:
    """Is this capture one flat colour, give or take?

    A real grid always has at least a header row and column separators. A capture that
    is a single colour means something opaque was covering the region, which happened
    here: the console window the automation is driven from sat over the app, and the
    screenshot was of the console's black body rather than the table.
    """
    from PIL import Image

    picture = Image.open(io.BytesIO(image)).convert("L").resize((64, 64))
    lightest, darkest = picture.getextrema()
    return (darkest - lightest) <= tolerance


GROUND_PROMPT = """\
This is a screenshot of part of a desktop application.

Locate each of the texts listed in the request. For each one, return its label exactly \
as given and the bounding box of that text on the image as box_2d, in the form \
[ymin, xmin, ymax, xmax] with every value normalized to the range 0 to 1000.

Only include labels you can actually see. Do not guess at positions of absent labels.
"""


def ground_boxes(image: bytes, labels: list[str], *,
                 what: str = "controls") -> dict[str, tuple[int, int, int, int]]:
    """Find where each label is painted, in pixel coordinates of the capture.

    This is the runtime-grounding fallback for things that are drawn rather than
    exposed: the caller captures a region, asks where the texts sit, and derives click
    points from the answer. Nothing is stored, so it survives layout changes the same
    way the other locators do.
    """
    from PIL import Image

    schema = {
        "type": "object",
        "properties": {
            "boxes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "label": {"type": "string"},
                        "box_2d": {"type": "array", "items": {"type": "integer"}},
                    },
                    "required": ["label", "box_2d"],
                },
            }
        },
        "required": ["boxes"],
    }

    wanted = ", ".join(repr(label) for label in labels)
    result = generate_json(
        [
            types.Part.from_bytes(data=image, mime_type="image/png"),
            GROUND_PROMPT + f"\nFind these texts: {wanted}",
        ],
        schema,
        what=what,
    )

    width, height = Image.open(io.BytesIO(image)).size
    found = {}
    for entry in result.get("boxes", []):
        label = entry.get("label", "")
        box = entry.get("box_2d", [])
        if label in labels and len(box) == 4:
            ymin, xmin, ymax, xmax = box
            found[label] = (
                int(xmin / 1000 * width), int(ymin / 1000 * height),
                int(xmax / 1000 * width), int(ymax / 1000 * height),
            )
    return found


def selection_row_center(image: bytes, min_fraction: float = 0.20) -> int | None:
    """The vertical centre of the highlighted row in a grid capture, if any.

    The selection band is a saturated blue on an otherwise light grid, so plain pixel
    counting finds it without a model call: a row of pixels belongs to the band when a
    decent fraction of it is much bluer than it is red or green.
    """
    from PIL import Image

    picture = Image.open(io.BytesIO(image)).convert("RGB")
    width, height = picture.size
    pixels = picture.load()

    band_rows = []
    step = max(1, width // 200)  # sampling every few pixels is plenty
    needed = (width // step) * min_fraction
    for y in range(height):
        hits = 0
        for x in range(0, width, step):
            r, g, b = pixels[x, y]
            if b > 150 and b - r > 80 and b - g > 60:
                hits += 1
        if hits >= needed:
            band_rows.append(y)

    if not band_rows:
        return None
    return (band_rows[0] + band_rows[-1]) // 2


def header_rule_y(image: bytes, *, search_depth: int = 200) -> int | None:
    """Where a drawn grid paints the dark rule under its column header.

    Returns the rule's y in the capture's own coordinates, so data rows start just below
    it. `None` when nothing stands out clearly enough to be trusted.

    This exists because the obvious way to find the header is wrong on these dialogs.
    Looking for the first band of header-coloured pixels finds the grid's top margin,
    which is painted the same shade and separated from the real header by a white line,
    and a click aimed from that lands *on* the header. On a filtered list showing one
    row, clicking the header re-sorts it and the only thing that changes is the little
    sort arrow: two pixels, at the top of the grid, which is indistinguishable by size
    from a row being selected. Nothing is then selected, Enter commits nothing, and the
    dialog reports only that it would not close.

    The rule itself is unambiguous. It is the one row that is dark across the whole
    width, where a row of text is dark only where its glyphs are: 312 sampled pixels
    against 92 for the next darkest row on a real capture.
    """
    from PIL import Image

    picture = Image.open(io.BytesIO(image)).convert("RGB")
    width, height = picture.size
    pixels = picture.load()
    step = max(1, width // 300)
    sampled = len(range(0, width, step))

    counts = sorted(
        ((sum(1 for x in range(0, width, step)
              if sum(pixels[x, y]) / 3 < 150), y)
         for y in range(min(height, search_depth))),
        reverse=True,
    )
    if not counts:
        return None

    best, runner_up = counts[0], (counts[1] if len(counts) > 1 else (0, 0))
    # Demanding both a wide line and a clear margin over everything else, because a
    # guess here puts clicks in the header, which is the failure this is here to stop.
    if best[0] < sampled * 0.25 or best[0] < runner_up[0] * 2:
        return None
    return best[1]


def changed_row_band(before: bytes, after: bytes,
                     min_fraction: float = 0.15) -> tuple[int, int] | None:
    """The vertical extent of what changed between two captures, or None.

    Colour-agnostic, and that matters more than it sounds. A selected row in the Items
    grid is a saturated blue that `selection_row_center` finds easily. A selected row in
    the "Select the address" dialog is a pale wash with a dotted focus border, and the
    same colour test sees nothing at all on a row that is plainly selected.

    The extent is returned rather than just the centre because the height is what
    distinguishes the two things a click here can do. Selecting a row changes one row.
    Clicking a column header re-sorts the list and repaints all of them, which changes
    pixels just as convincingly while leaving nothing selected.
    """
    from PIL import Image, ImageChops

    first = Image.open(io.BytesIO(before)).convert("RGB")
    second = Image.open(io.BytesIO(after)).convert("RGB")
    if first.size != second.size:
        return None

    diff = ImageChops.difference(first, second).convert("L")
    width, height = diff.size
    pixels = diff.load()
    step = max(1, width // 200)
    needed = (width // step) * min_fraction

    rows = [y for y in range(height)
            if sum(1 for x in range(0, width, step) if pixels[x, y] > 24) >= needed]
    if not rows:
        return None
    return rows[0], rows[-1]


def changed_row_center(before: bytes, after: bytes, min_fraction: float = 0.15) -> int | None:
    """The centre of the horizontal band that differs between two captures.

    Colour-agnostic selection detection: whatever a click did to the clicked row,
    that row is where the pixels changed. Immune to theme, focus state and the
    inactive-selection grey that defeats a colour test.
    """
    from PIL import Image, ImageChops

    a = Image.open(io.BytesIO(before)).convert("RGB")
    b = Image.open(io.BytesIO(after)).convert("RGB")
    if a.size != b.size:
        return None

    diff = ImageChops.difference(a, b).convert("L")
    width, height = diff.size
    pixels = diff.load()
    step = max(1, width // 200)
    needed = (width // step) * min_fraction

    rows = [y for y in range(height)
            if sum(1 for x in range(0, width, step) if pixels[x, y] > 24) >= needed]
    if not rows:
        return None
    return (rows[0] + rows[-1]) // 2


def _is_white(colour) -> bool:
    return all(channel >= 246 for channel in colour)


def _header_band(pixels, width: int, height: int):
    """The colour a drawn table's column header is painted in, and the rows it occupies.

    Both are derived rather than written down, so a change of theme or of display scale
    moves the numbers instead of breaking the read.
    """
    from collections import Counter

    # Sampled from the top few rows, which sit above the line where any label is painted
    # and so are pure background. Blank is excluded because SWT paints filler out to the
    # edge of the viewport past the last column, and on a wide editor there is more
    # filler than there is table.
    top = range(1, max(2, min(height, 1 + max(3, height // 12))))
    shades = Counter(
        pixels[x, y] for x in range(0, width, 2) for y in top
        if not _is_white(pixels[x, y])
    )
    if not shades:
        return None
    header = shades.most_common(1)[0][0]

    def row_is_header(y: int) -> bool:
        return sum(1 for x in range(0, width, 2) if pixels[x, y] == header) \
            >= (width / 2) * 0.05

    # Start from the first header row rather than from the top of the capture: a strip
    # opens with a border row or two that carry none of the header's colour.
    start = next((y for y in range(height) if row_is_header(y)), None)
    if start is None:
        return None
    bottom = next((y for y in range(start, height) if not row_is_header(y)), height)
    band = range(start, bottom)
    if len(band) < 4:
        return None
    return header, band


def column_edges(image: bytes, *, min_run: int = 8,
                 max_separator: int = 6) -> list[int]:
    """Where a drawn table's columns divide, read from a capture of its header strip.

    Deliberately model-free, and the reason is worth stating because the model was tried
    first. `ground_boxes` locates text reliably on a normally proportioned screenshot,
    and does not on this one: the Items header is about 2300x60, and on a strip that
    elongated the returned boxes came back roughly twice too far right. That is what sent
    the first attempt at line entry into the VAT column, where it typed quantities into a
    dropdown and reported that nothing had changed.

    Pixels have no such problem. SWT paints the column headers in one flat colour and
    leaves the dividers between them unpainted, so a divider is a narrow run of x where
    that colour is absent. The row-header corner above the Pos. column is painted a
    different, lighter shade, which is what marks the left edge of the first real column.

    Returns edges in the capture's own coordinates, left to right, so `len(edges) - 1`
    columns are described. Colours are sampled rather than written down, so a theme
    change moves the numbers instead of breaking the read.
    """
    from collections import Counter

    from PIL import Image

    picture = Image.open(io.BytesIO(image)).convert("RGB")
    width, height = picture.size
    pixels = picture.load()

    found = _header_band(pixels, width, height)
    if found is None:
        return []
    header, band = found
    depth = len(band)

    def is_header(x: int) -> bool:
        # Presence, not dominance: much of a header cell's band is glyph pixels where
        # its label is painted, and that cell is still part of the header.
        return sum(1 for y in band if pixels[x, y] == header) >= depth * 0.25

    columns = [x for x in range(width) if is_header(x)]
    if not columns:
        return []

    left, right = columns[0], columns[-1]
    edges, x = [left - 1], left
    while x <= right:
        if is_header(x):
            x += 1
            continue
        gap_start = x
        while x <= right and not is_header(x):
            x += 1
        if x - gap_start > max_separator:
            # Too wide to be a divider, so the table has already ended and what follows
            # is the blank filler SWT paints out to the edge of the viewport.
            break
        edges.append((gap_start + x - 1) // 2)

    edges.append(right + 1)

    # SWT paints the filler past the last column in the same colour as the header and
    # puts no divider before it, so the final span swallows it and can come back several
    # times too wide. Nothing here edits the last column, but leaving the span honest
    # keeps the geometry usable for anything that reads it later.
    if len(edges) >= 4:
        widths = sorted(edges[index + 1] - edges[index]
                        for index in range(len(edges) - 2))
        typical = widths[len(widths) // 2]
        if edges[-1] - edges[-2] > typical * 1.8:
            edges[-1] = edges[-2] + typical

    return edges


def read_table(image: bytes, columns: list[str], *, what: str = "table") -> list[dict]:
    """Read a drawn table's rows into dicts keyed by column name."""
    if looks_blank(image):
        # Refusing is important: sent to the model, a covered grid reads as "no rows",
        # and a no-rows answer sends the flow off to create a duplicate record.
        raise ExtractionError(
            f"the capture of {what} is a blank rectangle; something is covering the "
            f"application window"
        )

    result = generate_json(
        [
            types.Part.from_bytes(data=image, mime_type="image/png"),
            READ_TABLE_PROMPT,
        ],
        table_schema(columns),
        what=what,
    )
    return result.get("rows", [])
