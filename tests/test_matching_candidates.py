"""Candidate matching and the verification that backs it up.

The selector lists one row per address, so a debtor with a separate delivery address
appears as a row with no company and the wrong postcode. Narrowing on the contact name
is what finds it; the address the Order populates afterwards is what proves it.
"""

import pytest

from src.matching import debtor_candidate, debtor_matches, missing_from_address_block


def delivery_row(**overrides) -> dict:
    """What our saved debtor actually looks like in the selector.

    Company blank and the delivery postcode, exactly as Fakturama listed it.
    """
    row = {
        "No.": "CUST000001",
        "First Name": "Marta",
        "Name": "Klein",
        "Company": "",
        "ZIP": "10553",
        "City": "Berlin",
    }
    return row | overrides


class TestDebtorCandidate:
    def test_finds_the_debtor_the_brief_rule_misses(self, order):
        row = delivery_row()
        # The five-column rule cannot match this row, which is what caused duplicates.
        assert not debtor_matches(row, order.debtor)
        assert debtor_candidate(row, order.debtor)

    def test_still_matches_a_plain_billing_row(self, order):
        row = delivery_row(Company="Northstar Office GmbH", ZIP="10117")
        assert debtor_candidate(row, order.debtor)

    @pytest.mark.parametrize("column, wrong", [("First Name", "Martina"),
                                               ("Name", "Kleinert")])
    def test_a_different_person_is_not_a_candidate(self, order, column, wrong):
        assert not debtor_candidate(delivery_row(**{column: wrong}), order.debtor)

    def test_same_surname_different_forename_is_not_a_candidate(self, order):
        # Two Kleins at one company must not collapse into one another.
        assert not debtor_candidate(delivery_row(**{"First Name": "Jonas"}),
                                    order.debtor)


class TestAddressVerification:
    def test_a_matching_block_is_complete(self, order):
        block = ("Northstar Office GmbH\nMarta Klein\nFriedrichstrasse 88\n"
                 "DE-10117 Berlin\nGermany")
        assert missing_from_address_block(block, order.debtor) == []

    def test_the_wrong_customer_is_caught(self, order):
        block = "Southstar Retail AG\nMarta Klein\nHauptstrasse 2\n99999 Hamburg"
        missing = missing_from_address_block(block, order.debtor)
        assert any("company" in item for item in missing)
        assert any("street" in item for item in missing)

    def test_the_right_person_at_the_wrong_address_is_caught(self, order):
        # Name matched, so selection succeeded, but this is a different site.
        block = ("Northstar Office GmbH\nMarta Klein\nBeusselstrasse 44\n"
                 "10553 Berlin\nGermany")
        missing = missing_from_address_block(block, order.debtor)
        assert any("street" in item for item in missing)
        assert any("zip" in item for item in missing)

    def test_an_empty_block_reports_everything(self, order):
        assert len(missing_from_address_block("", order.debtor)) >= 5
