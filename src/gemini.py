"""The only file that knows which model provider we use.

Two callers: reading the order image, and reading tables that Fakturama draws itself and
does not expose to UIA. Swapping provider means rewriting this file and nothing else.
"""

import json
import os
import time

import httpx
from dotenv import load_dotenv
from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from src.errors import ExtractionError

DEFAULT_MODEL = "gemini-flash-latest"

# The free tier hands out 503s when the model is busy and 429s when we are. Both clear
# on their own, so they are worth waiting out rather than failing a run over.
#
# Patient on purpose. These calls sit in the middle of a long UI flow that has already
# created master data and cannot be resumed from where it stopped, so throwing away ten
# minutes of work rather than waiting half a minute is a bad trade. Roughly a minute of
# total backoff across six attempts.
_RETRYABLE = {429, 500, 503}
_MAX_ATTEMPTS = 6
_MAX_BACKOFF = 20


def client() -> genai.Client:
    load_dotenv()
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ExtractionError(
            "GEMINI_API_KEY is not set. Put it in a .env file at the repo root."
        )
    return genai.Client(api_key=api_key)


def generate_json(contents: list, schema: dict, *, what: str = "response") -> dict:
    """Ask for JSON matching `schema` and hand back the parsed object.

    The schema is enforced by the API rather than hoped for, so a missing field is a
    request failure instead of a silent None much further downstream.
    """
    model = os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=schema,
        # Deterministic, so re-reading the same picture gives the same answer and a
        # difference in output means something actually changed.
        temperature=0,
        # We pass no tools, and leaving this on makes the SDK log a warning about it.
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )

    api = client()
    for attempt in range(_MAX_ATTEMPTS):
        last = attempt == _MAX_ATTEMPTS - 1
        try:
            response = api.models.generate_content(
                model=model, contents=contents, config=config
            )
            break
        except genai_errors.APIError as exc:
            if exc.code not in _RETRYABLE or last:
                raise ExtractionError(
                    f"{model} failed reading {what} after {attempt + 1} attempts: {exc}"
                ) from exc
            time.sleep(min(2**attempt, _MAX_BACKOFF))
        except httpx.TransportError as exc:
            # DNS and connection failures arrive as raw transport errors rather than as
            # an APIError with a status, so they slip past the check above. One turned up
            # as "getaddrinfo failed" mid-run right after restarting Fakturama, and it
            # cleared on its own. Worth waiting out for the same reason as a 503.
            if last:
                raise ExtractionError(
                    f"could not reach {model} for {what} after {attempt + 1} "
                    f"attempts: {exc!r}"
                ) from exc
            time.sleep(min(2**attempt, _MAX_BACKOFF))

    if not response.text:
        raise ExtractionError(f"model returned nothing for {what}")

    try:
        return json.loads(response.text)
    except json.JSONDecodeError as exc:
        raise ExtractionError(f"model returned invalid JSON for {what}: {exc}") from exc
