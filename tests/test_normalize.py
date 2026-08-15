from datetime import date
from decimal import Decimal

import pytest

from src.errors import ExtractionError
from src.extract.normalize import to_date, to_decimal, to_order_data


class TestToDecimal:
    def test_plain(self):
        assert to_decimal("1234.50") == Decimal("1234.50")

    def test_strips_currency_and_percent(self):
        assert to_decimal("EUR 570.00") == Decimal("570.00")
        assert to_decimal("19%") == Decimal("19")

    def test_german_convention(self):
        assert to_decimal("1.234,56") == Decimal("1234.56")

    def test_anglo_convention(self):
        assert to_decimal("1,234.56") == Decimal("1234.56")

    def test_comma_as_decimal_point(self):
        assert to_decimal("1,50") == Decimal("1.50")

    def test_comma_as_thousands_separator(self):
        # Three digits behind the comma cannot be cents.
        assert to_decimal("1,500") == Decimal("1500")

    def test_rejects_junk(self):
        with pytest.raises(ExtractionError):
            to_decimal("n/a")


class TestToDate:
    def test_iso(self):
        assert to_date("2026-07-14") == date(2026, 7, 14)

    def test_german(self):
        assert to_date("14.07.2026") == date(2026, 7, 14)

    def test_rejects_junk(self):
        with pytest.raises(ExtractionError):
            to_date("July the 14th")


class TestToOrderData:
    def test_reads_the_sample_order(self, order):
        assert order.external_reference == "WEB-2026-0714-A17"
        assert order.order_date == date(2026, 7, 14)
        assert order.currency == "EUR"
        assert len(order.items) == 2

    def test_delivery_address_differs_from_billing(self, order):
        # The sample ships to a warehouse, so the Debtor needs a second address rather
        # than the Main address carrying both roles.
        assert not order.debtor.delivery_is_billing
        assert order.debtor.delivery.name == "Northstar Office Warehouse"

    def test_unpaid_order_carries_no_payment_date(self, raw_order):
        raw_order["payment"] = {"method": "Bank Transfer", "is_paid": False,
                                "paid_on": "2026-07-18"}
        order = to_order_data(raw_order)
        # Even though the raw payload had a date, an unpaid document must not keep one.
        assert order.payment.paid_on is None

    def test_paid_without_a_date_is_rejected(self, raw_order):
        raw_order["payment"] = {"method": "Bank Transfer", "is_paid": True,
                                "paid_on": ""}
        with pytest.raises(ExtractionError, match="paid"):
            to_order_data(raw_order)

    def test_no_items_is_rejected(self, raw_order):
        raw_order["items"] = []
        with pytest.raises(ExtractionError, match="item"):
            to_order_data(raw_order)
