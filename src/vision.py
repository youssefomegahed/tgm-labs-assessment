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

    image = ImageGrab.grab(bbox=box, all_screens=True)
    if save_to:
        image.save(save_to)  # keeping the evidence for the run log

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def capture(element, save_to: str | None = None) -> bytes:
    rect = element.rectangle()
    return capture_region((rect.left, rect.top, rect.right, rect.bottom), save_to)


def read_table(image: bytes, columns: list[str], *, what: str = "table") -> list[dict]:
    """Read a drawn table's rows into dicts keyed by column name."""
    result = generate_json(
        [
            types.Part.from_bytes(data=image, mime_type="image/png"),
            READ_TABLE_PROMPT,
        ],
        table_schema(columns),
        what=what,
    )
    return result.get("rows", [])
