"""Comparing what we wrote against what the field shows afterwards.

Fakturama reformats as it commits, so a strict string check rejects values it actually
accepted. The comparison has to ignore presentation without ignoring meaning.
"""

from src.uia.actions import _same_value


class TestSameValue:
    def test_identical(self):
        assert _same_value("Bank Transfer", "Bank Transfer")

    def test_percent_added_on_commit(self):
        # What the Cash discount field does to "0".
        assert _same_value("0%", "0")

    def test_currency_added_on_commit(self):
        assert _same_value("$0.00", "0.00")

    def test_trailing_zeros_added(self):
        assert _same_value("10.00", "10")

    def test_thousands_separator_added(self):
        assert _same_value("1,234.50", "1234.50")

    def test_a_different_number_is_still_caught(self):
        assert not _same_value("10%", "0")

    def test_a_blank_field_is_still_caught(self):
        assert not _same_value("", "0")

    def test_text_is_compared_exactly(self):
        # Only numbers get the tolerance; names must match outright.
        assert not _same_value("Bank Transfers", "Bank Transfer")

    def test_text_that_merely_looks_close_is_caught(self):
        assert not _same_value("Credit card", "Credit transfer")
