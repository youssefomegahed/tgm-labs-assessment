"""What counts as an exact match, and what counts as ambiguous.

The brief hangs a lot on this. A Debtor is a match only when Company, First Name, Name,
ZIP and City all agree. A Product matches on SKU alone. A VAT rate has to agree on
name, value and e-invoice code. Getting any of these wrong means either creating a
duplicate master record or attaching the order to the wrong one, so the rules live here
on their own, away from the UI code, where they can be tested.

Rows arrive as plain dicts of column name to displayed text, read out of whichever
Fakturama list we are looking at. Keeping them dicts means this module never has to
know how the reading was done.
"""

import re

from src.errors import ManualReviewRequired
from src.extract.normalize import to_decimal
from src.models import Debtor, LineItem

# SWT tables clip long cells and mark them. Figure 1 in the brief shows the Company
# column reading "Northstar Office ..." for a customer whose real name is longer, so a
# straight equality test on that column would never match.
_TRUNCATION = re.compile(r"\s*(\.\.\.|…)$")


def cell_matches(cell: str, expected: str) -> bool:
    """Compare one displayed cell against the value we extracted.

    Case and surrounding whitespace are ignored: they vary with how Fakturama renders a
    column, and treating "BERLIN" as a different city from "Berlin" would send us off
    creating duplicates. A clipped cell matches when the expected value starts with it.
    """
    cell = re.sub(r"\s+", " ", cell or "").strip()
    expected = re.sub(r"\s+", " ", expected or "").strip()

    if _TRUNCATION.search(cell):
        prefix = _TRUNCATION.sub("", cell)
        return bool(prefix) and expected.casefold().startswith(prefix.casefold())

    return cell.casefold() == expected.casefold()


def debtor_matches(row: dict, debtor: Debtor) -> bool:
    """The five columns the brief names, all of them."""
    return (
        cell_matches(row.get("Company", ""), debtor.company)
        and cell_matches(row.get("First Name", ""), debtor.contact.first_name)
        and cell_matches(row.get("Name", ""), debtor.contact.last_name)
        and cell_matches(row.get("ZIP", ""), debtor.billing.zip_code)
        and cell_matches(row.get("City", ""), debtor.billing.city)
    )


def product_matches(row: dict, sku: str) -> bool:
    """SKU only. Description and price are allowed to differ from the order line."""
    return cell_matches(row.get("Item No.", ""), sku)


def payment_matches(row: dict, method: str) -> bool:
    return cell_matches(row.get("Name", ""), method)


def vat_matches(row: dict, item: LineItem) -> bool:
    """Name, value and e-invoice code have to agree.

    The value is compared numerically because Fakturama displays it as "19.00 %" while
    the source document prints "19%". The code is not shown in the VAT list, so the
    caller has to open the row and put it in the dict. A row without a code counts as
    not matching rather than as a pass, so a missing read can never be mistaken for a
    confirmed one.
    """
    if not cell_matches(row.get("Name", ""), item.vat_rate_name):
        return False

    if row.get("code") is None:
        return False
    if not str(row["code"]).strip().upper().startswith("S"):
        return False

    try:
        return to_decimal(row.get("Value", "")) == item.vat_percent
    except Exception:
        return False


def resolve_one(rows: list[dict], predicate, *, what: str, stage: str = "") -> dict | None:
    """Pick the single matching row.

    Returns None when nothing matches, which is the caller's signal to create the
    record. Raises when more than one matches, because choosing between them is a
    judgement the brief reserves for a person.
    """
    matches = [row for row in rows if predicate(row)]

    if len(matches) > 1:
        raise ManualReviewRequired(
            f"{len(matches)} rows match {what}, cannot choose between them: {matches}",
            stage=stage,
        )

    return matches[0] if matches else None
