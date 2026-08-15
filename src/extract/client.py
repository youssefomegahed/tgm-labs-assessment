"""Reading the order image into a raw dict."""

import pathlib

from google.genai import types

from src.errors import ExtractionError
from src.extract.prompt import EXTRACTION_PROMPT
from src.extract.schema import ORDER_SCHEMA
from src.gemini import generate_json

_MIME_BY_SUFFIX = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


def extract_order(image_path: str | pathlib.Path) -> dict:
    """Read the order image and return the raw extracted dict.

    Raw meaning strings, exactly as the model transcribed them. Turning those into
    Decimals and dates is normalize.py's job.
    """
    path = pathlib.Path(image_path)
    if not path.is_file():
        raise ExtractionError(f"no such image: {path}")

    mime = _MIME_BY_SUFFIX.get(path.suffix.lower())
    if mime is None:
        raise ExtractionError(f"unsupported image type: {path.suffix}")

    return generate_json(
        [
            types.Part.from_bytes(data=path.read_bytes(), mime_type=mime),
            EXTRACTION_PROMPT,
        ],
        ORDER_SCHEMA,
        what="the order image",
    )
