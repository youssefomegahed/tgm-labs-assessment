"""The Items grid's column detection, against a real capture of it.

Worth pinning with a fixture rather than a synthetic image. This code exists because the
vision-model route it replaced was wrong in a way that produced no error: it grounded
the "Qty." header about twice too far right on a very wide, thin strip, so double-clicks
landed in the VAT column and quantities were typed into a dropdown that discarded them.
A test that only checked "returns some edges" would have passed for that version too, so
these assert the actual dividers, cross-checked against cell-editor rectangles UIA
reported for the same grid: the Name cell at 288..486 and the VAT cell at 488..686 in
this capture's coordinates.
"""

import pathlib

import pytest

from src import vision

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "items-grid.png"


@pytest.fixture(scope="module")
def grid() -> bytes:
    return FIXTURE.read_bytes()


def test_finds_one_edge_per_column_boundary(grid):
    assert vision.column_edges(grid) == [87, 286, 486, 686, 886, 1086]


def test_describes_five_data_columns(grid):
    edges = vision.column_edges(grid)
    assert len(edges) - 1 == 5, "Pos. is a row header, not one of the data columns"


def test_the_qty_column_is_the_leftmost_and_not_the_vat_one(grid):
    edges = vision.column_edges(grid)
    left, right = edges[0], edges[1]
    centre = (left + right) // 2
    # The bug this replaced aimed at 599 in these coordinates, inside VAT at 486..686.
    assert left < centre < right
    assert centre < 486, "the Qty column must not overlap VAT"


def test_columns_line_up_with_the_cell_editors_uia_reported(grid):
    edges = vision.column_edges(grid)
    spans = {name: (edges[index], edges[index + 1]) for index, name in
             enumerate(["Qty.", "Name", "VAT", "U.Price", "Price"])}

    # Both editors sit a pixel or two inside their cell, so containment is the check.
    name_left, name_right = spans["Name"]
    assert name_left <= 288 and 486 <= name_right + 1

    vat_left, vat_right = spans["VAT"]
    assert vat_left <= 488 and 686 <= vat_right + 1


def test_the_trailing_filler_does_not_swallow_the_last_column(grid):
    edges = vision.column_edges(grid)
    widths = [edges[i + 1] - edges[i] for i in range(len(edges) - 1)]
    # SWT paints the same grey past the last column out to the viewport edge, and the
    # capture is 2321 wide against a table of about 1000.
    assert max(widths) < 400, f"a column absorbed the filler: {widths}"


def test_a_blank_image_is_refused_rather_than_guessed_at():
    import io

    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (400, 120), "white").save(buffer, format="PNG")
    assert vision.column_edges(buffer.getvalue()) == []
