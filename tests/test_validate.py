from decimal import Decimal

import pytest

from src.errors import ManualReviewRequired
from src.extract.normalize import to_order_data
from src.extract.validate import assert_consistent, check_order


class TestCheckOrder:
    def test_the_sample_order_adds_up(self, order):
        failed = [check for check in check_order(order) if not check.ok]
        assert failed == []

    def test_covers_every_line_plus_the_three_totals(self, order):
        names = [check.name for check in check_order(order)]
        assert names == [
            "line 1 (CHR-ERG-01)",
            "line 2 (MAT-DESK-02)",
            "net total",
            "vat total",
            "gross total",
        ]

    def test_discount_is_applied_to_the_line(self, order):
        chair = order.items[0]
        # 2 x 250.00 less 10% is 450.00, not 500.00.
        assert chair.computed_net == Decimal("450.00")

    def test_a_misread_line_total_is_caught(self, raw_order):
        raw_order["items"][0]["line_net"] = "500.00"
        checks = {c.name: c for c in check_order(to_order_data(raw_order))}
        assert not checks["line 1 (CHR-ERG-01)"].ok
        assert checks["line 1 (CHR-ERG-01)"].delta == Decimal("50.00")

    def test_a_misread_vat_total_is_caught(self, raw_order):
        raw_order["vat_total"] = "108.03"  # two digits transposed
        checks = {c.name: c for c in check_order(to_order_data(raw_order))}
        assert not checks["vat total"].ok

    def test_vat_is_rounded_once_per_rate(self, raw_order):
        """Lines at the same rate round together, not separately.

        Each of these three nets comes to 1.995 of VAT, which rounds up to 2.00 on its
        own, so summing per line gives 6.00. Rounding the rate as a whole gives 5.99,
        and 5.99 is what the document prints. Rounding per line would report a false
        mismatch here.
        """
        template = raw_order["items"][0]
        raw_order["items"] = [
            dict(template, position=n, sku=f"SKU-{n}", quantity="1",
                 unit_net="10.50", discount_percent="0", line_net="10.50")
            for n in (1, 2, 3)
        ]
        raw_order["net_total"] = "31.50"
        raw_order["vat_total"] = "5.99"
        raw_order["gross_total"] = "37.49"

        checks = {c.name: c for c in check_order(to_order_data(raw_order))}
        assert checks["vat total"].computed == Decimal("5.99")
        assert checks["vat total"].ok


class TestAssertConsistent:
    def test_passes_quietly_on_good_data(self, order):
        assert len(assert_consistent(order)) == 5

    def test_stops_the_flow_on_bad_arithmetic(self, raw_order):
        raw_order["gross_total"] = "999.99"
        with pytest.raises(ManualReviewRequired, match="do not add up"):
            assert_consistent(to_order_data(raw_order))
