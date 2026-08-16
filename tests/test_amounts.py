"""Reading a displayed amount back as a number, whatever locale drew it.

Fakturama formats money with the currency locale set in its preferences, and that is not
a hypothetical variable: it changed under me mid-project, from "$250.00" to "250,00 EUR"
to a right-to-left locale, and each shape broke a different assumption. Since every
totals check in the flow runs through this one function, a shape it cannot read reports
as "the document does not match" rather than as "I could not read this", which sends you
looking in entirely the wrong place.
"""

from decimal import Decimal

import pytest

from src.uia.actions import _as_number, _same_value


@pytest.mark.parametrize("shown, expected", [
    # Symbol first, which is how a US locale draws it.
    ("$250.00", "250.00"),
    ("$0.00", "0"),
    # Symbol last, after a non-breaking space, which is how a German one does. Note the
    # separators swap roles as well as the symbol moving.
    ("620,00 €", "620.00"),
    ("-1.234,57 €", "-1234.57"),
    ("737,80 €", "737.80"),
    # A right-to-left locale wraps the sign in directional marks.
    ("‎-‎250,00 ؋", "-250.00"),
    # Percentages, including the negative Fakturama shows a line discount as.
    ("0%", "0"),
    ("-10.00 %", "-10"),
    ("19%", "19"),
])
def test_reads_an_amount_whatever_decorates_it(shown, expected):
    assert _as_number(shown) == Decimal(expected)


@pytest.mark.parametrize("shown", [
    "VAT 19%",
    "Ergonomic Des...",
    "Free of shipping costs",
    "",
    None,
    # Digits this cannot parse must be refused rather than guessed at. These are
    # Extended Arabic-Indic digits, which is what Fakturama emitted with its currency
    # locale on Afghanistan, and a wrong number here would be saved into an invoice.
    "۲۵۰٫۰۰",
])
def test_refuses_anything_it_cannot_read(shown):
    assert _as_number(shown) is None


def test_a_committed_value_is_compared_by_meaning_across_locales():
    # What the flow actually does: write "620.00", let Fakturama reformat it, and check
    # the two still mean the same thing.
    assert _same_value("620,00 €", "620.00")
    assert _same_value("$620.00", "620.00")
    assert not _same_value("620,00 €", "621.00")


def test_text_is_still_compared_exactly():
    # The loosening above applies to numbers only. A product name that came back
    # different is a real mismatch, not a formatting difference.
    assert not _same_value("Ergonomic Desk Chair", "Ergonomic Desk Chairs")
    assert _same_value("Bank Transfer", "Bank Transfer")
