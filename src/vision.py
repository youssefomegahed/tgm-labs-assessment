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
