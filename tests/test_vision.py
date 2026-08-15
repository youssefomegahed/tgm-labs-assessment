import io

from PIL import Image

from src.vision import looks_blank


def png(color_rows) -> bytes:
    """A tiny image built from rows of grey values."""
    height = len(color_rows)
    width = len(color_rows[0])
    picture = Image.new("L", (width, height))
    picture.putdata([value for row in color_rows for value in row])
    buffer = io.BytesIO()
    picture.save(buffer, format="PNG")
    return buffer.getvalue()


class TestLooksBlank:
    def test_a_flat_black_capture_is_blank(self):
        # What the console's body actually produced in this project.
        assert looks_blank(png([[12] * 40] * 40))

    def test_a_flat_white_capture_is_blank(self):
        assert looks_blank(png([[250] * 40] * 40))

    def test_a_header_row_over_a_white_body_is_not_blank(self):
        # The empty address selector: dark header text, white rows below. Empty of data
        # is not the same as blank, and must stay readable.
        header = [40] * 40
        body = [245] * 40
        assert not looks_blank(png([header] * 4 + [body] * 36))
