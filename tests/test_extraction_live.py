"""Does the model actually read the document correctly?

This one calls the API, so it is opt-in. Everything else in the suite runs offline.

    RUN_LIVE_TESTS=1 pytest tests/test_extraction_live.py
"""

import json
import os
import pathlib

import pytest

from src.extract.client import extract_order
from src.extract.normalize import to_order_data
from src.extract.validate import check_order

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_LIVE_TESTS") != "1",
    reason="set RUN_LIVE_TESTS=1 to call the model",
)

ORDER_IMAGE = pathlib.Path(__file__).parent.parent / "data" / "order.png"


@pytest.fixture(scope="module")
def extracted() -> dict:
    """One API call shared by the tests below."""
    return extract_order(ORDER_IMAGE)


def flatten(value: dict, prefix: str = "") -> dict:
    flat = {}
    for key, item in value.items():
        path = f"{prefix}{key}"
        if isinstance(item, dict):
            flat |= flatten(item, f"{path}.")
        elif isinstance(item, list):
            for index, element in enumerate(item):
                flat |= flatten(element, f"{path}[{index}].")
        else:
            flat[path] = item
    return flat


def test_every_field_matches_the_ground_truth(extracted, raw_order):
    raw_order.pop("_comment", None)
    expected, actual = flatten(raw_order), flatten(extracted)

    differences = {
        key: (expected.get(key), actual.get(key))
        for key in expected | actual
        if expected.get(key) != actual.get(key)
    }
    assert differences == {}


def test_extraction_is_internally_consistent(extracted):
    order = to_order_data(extracted)
    assert [check for check in check_order(order) if not check.ok] == []


def test_reads_both_addresses_separately(extracted):
    order = to_order_data(extracted)
    # The easiest mistake on this document is copying the billing block into both.
    assert not order.debtor.delivery_is_billing
