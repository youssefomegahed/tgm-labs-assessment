import json
import pathlib

import pytest

from src.extract.normalize import to_order_data

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


@pytest.fixture
def raw_order() -> dict:
    """The ground truth read by hand off data/order.png."""
    return json.loads((FIXTURES / "expected_order.json").read_text())


@pytest.fixture
def order(raw_order):
    return to_order_data(raw_order)
