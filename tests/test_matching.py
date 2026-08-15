import pytest

from src.errors import ManualReviewRequired
from src.matching import (
    cell_matches,
    debtor_matches,
    payment_matches,
    product_matches,
    resolve_one,
    vat_matches,
)


def debtor_row(**overrides) -> dict:
    row = {
        "Company": "Northstar Office GmbH",
        "First Name": "Marta",
        "Name": "Klein",
        "ZIP": "10117",
        "City": "Berlin",
    }
    return row | overrides


class TestCellMatches:
    def test_exact(self):
        assert cell_matches("Berlin", "Berlin")

    def test_ignores_case_and_padding(self):
        assert cell_matches("  BERLIN ", "Berlin")

    def test_clipped_cell_matches_on_prefix(self):
        # What figure 1 actually shows in the Company column.
        assert cell_matches("Northstar Office ...", "Northstar Office GmbH")

    def test_clipped_cell_with_ellipsis_character(self):
        assert cell_matches("Northstar Office …", "Northstar Office GmbH")

    def test_clipped_cell_still_has_to_be_a_prefix(self):
        assert not cell_matches("Southstar Office ...", "Northstar Office GmbH")

    def test_different_value(self):
        assert not cell_matches("Hamburg", "Berlin")


class TestDebtorMatches:
    def test_all_five_columns_agree(self, order):
        assert debtor_matches(debtor_row(), order.debtor)

    @pytest.mark.parametrize(
        "column, wrong",
        [
            ("Company", "Southstar Office GmbH"),
            ("First Name", "Martina"),
            ("Name", "Kleinert"),
            ("ZIP", "10553"),
            ("City", "Hamburg"),
        ],
    )
    def test_any_single_column_disagreeing_is_not_a_match(self, order, column, wrong):
        assert not debtor_matches(debtor_row(**{column: wrong}), order.debtor)

    def test_zip_comes_from_the_billing_address(self, order):
        # 10553 is the delivery ZIP. Matching on it would pick the wrong debtor.
        assert not debtor_matches(debtor_row(ZIP="10553"), order.debtor)


class TestProductMatches:
    def test_exact_sku(self):
        assert product_matches({"Item No.": "CHR-ERG-01"}, "CHR-ERG-01")

    def test_near_miss_is_not_a_match(self):
        assert not product_matches({"Item No.": "CHR-ERG-02"}, "CHR-ERG-01")


class TestVatMatches:
    def test_name_value_and_code_agree(self, order):
        row = {"Name": "VAT 19%", "Value": "19.00 %", "code": "S (Standard rate)"}
        assert vat_matches(row, order.items[0])

    def test_value_must_agree_with_the_name(self, order):
        row = {"Name": "VAT 19%", "Value": "7.00 %", "code": "S (Standard rate)"}
        assert not vat_matches(row, order.items[0])

    def test_unread_code_is_not_a_pass(self, order):
        row = {"Name": "VAT 19%", "Value": "19.00 %"}
        assert not vat_matches(row, order.items[0])

    def test_non_standard_code_is_rejected(self, order):
        row = {"Name": "VAT 19%", "Value": "19.00 %", "code": "Z (Zero rated)"}
        assert not vat_matches(row, order.items[0])


class TestPaymentMatches:
    def test_exact_name(self):
        assert payment_matches({"Name": "Bank Transfer"}, "Bank Transfer")

    def test_different_method(self):
        assert not payment_matches({"Name": "Credit Card"}, "Bank Transfer")


class TestResolveOne:
    def test_nothing_matches_returns_none(self, order):
        rows = [debtor_row(Company="Someone Else GmbH")]
        assert resolve_one(rows, lambda r: debtor_matches(r, order.debtor),
                           what="debtor") is None

    def test_one_match_is_returned(self, order):
        rows = [debtor_row(Company="Someone Else GmbH"), debtor_row()]
        found = resolve_one(rows, lambda r: debtor_matches(r, order.debtor),
                            what="debtor")
        assert found["Company"] == "Northstar Office GmbH"

    def test_two_matches_stop_for_manual_review(self, order):
        rows = [debtor_row(), debtor_row()]
        with pytest.raises(ManualReviewRequired, match="2 rows match"):
            resolve_one(rows, lambda r: debtor_matches(r, order.debtor),
                        what="debtor")
