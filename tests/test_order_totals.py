"""The check that stops a wrong Order from being saved.

This is the last gate before master data becomes a document, so it needs to catch a
mismatch and not be fooled by Fakturama's own formatting.
"""

import pytest

from src.errors import ManualReviewRequired
from src.flow.order import _confirm_totals


def shown(net="$570.00", vat="$108.30", total="$678.30") -> dict:
    """Totals as the editor displays them: currency symbol, US locale."""
    return {"total_net": net, "vat": vat, "total": total, "discount": "0%"}


class TestConfirmTotals:
    def test_matching_totals_pass(self, order):
        _confirm_totals(shown(), order, log=lambda _m: None)

    def test_currency_formatting_is_not_a_mismatch(self, order):
        # The guest locale prints dollars for a EUR document. The numbers are what
        # matter; the symbol is not something the brief asks us to change.
        _confirm_totals(shown(net="570.00", vat="108.30", total="678.30"),
                        order, log=lambda _m: None)

    def test_an_order_still_missing_quantities_is_caught(self, order):
        # What the Order actually holds before line quantities are set: two lines at
        # quantity one. This must not be allowed to save.
        with pytest.raises(ManualReviewRequired, match="does not match the document"):
            _confirm_totals(shown(net="$290.00", vat="$55.10", total="$345.10"),
                            order, log=lambda _m: None)

    def test_a_missing_discount_is_caught(self, order):
        # Right quantities, but line 1's 10% discount not applied: 620.00 not 570.00.
        with pytest.raises(ManualReviewRequired, match="total_net"):
            _confirm_totals(shown(net="$620.00", vat="$117.80", total="$737.80"),
                            order, log=lambda _m: None)

    def test_an_empty_field_is_caught(self, order):
        with pytest.raises(ManualReviewRequired):
            _confirm_totals(shown(net=""), order, log=lambda _m: None)

    def test_the_message_names_what_disagreed(self, order):
        with pytest.raises(ManualReviewRequired) as caught:
            _confirm_totals(shown(vat="$1.00"), order, log=lambda _m: None)
        assert "vat" in str(caught.value)
        assert "108.30" in str(caught.value)
