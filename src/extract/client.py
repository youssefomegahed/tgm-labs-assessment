"""The one file that knows which model provider we use.

Everything downstream works on OrderData, so swapping provider means rewriting this
file and nothing else.
"""

import json
import os
import pathlib

from dotenv import load_dotenv
from google import genai
from google.genai import types

from src.errors import ExtractionError
from src.extract.prompt import EXTRACTION_PROMPT
from src.extract.schema import ORDER_SCHEMA

DEFAULT_MODEL = "gemini-flash-latest"

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

    load_dotenv()
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ExtractionError(
            "GEMINI_API_KEY is not set. Put it in a .env file at the repo root."
        )

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=os.environ.get("GEMINI_MODEL", DEFAULT_MODEL),
        contents=[
            types.Part.from_bytes(data=path.read_bytes(), mime_type=mime),
            EXTRACTION_PROMPT,
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=ORDER_SCHEMA,
            # Deterministic, so a re-run on the same image gives the same reading and a
            # diff in the output means something actually changed.
            temperature=0,
        ),
    )

    if not response.text:
        raise ExtractionError("model returned no content")

    try:
        return json.loads(response.text)
    except json.JSONDecodeError as exc:
        raise ExtractionError(f"model returned invalid JSON: {exc}") from exc
