"""Raw extracted strings into typed OrderData.

The prompt asks for clean values, but a model is not a parser and this is the boundary
where we stop trusting it. Everything here is defensive and, being pure, is the easiest
part of the system to test.
"""

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from src.errors import ExtractionError
from src.models import Address, Contact, Debtor, LineItem, OrderData, Payment

# Anything that is not a digit, separator or sign is noise: currency symbols, codes,
# stray percent signs, non-breaking spaces from a copy-paste.
_NUMBER_NOISE = re.compile(r"[^\d,.\-]")

_DATE_FORMATS = ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y")


def clean(raw: object) -> str:
    """Trim, and collapse runs of whitespace that OCR tends to introduce."""
    return re.sub(r"\s+", " ", str(raw or "")).strip()


def to_decimal(raw: object, *, field: str = "number") -> Decimal:
    """Parse a printed number, tolerating either decimal convention.

    German documents are as likely to print 1.234,56 as 1,234.56, and we would rather
    read both than assume the model normalized it for us.
    """
    text = _NUMBER_NOISE.sub("", str(raw or ""))
    if not text:
        raise ExtractionError(f"{field}: no number in {raw!r}")

    if "," in text and "." in text:
        # Whichever separator appears last is the decimal point.
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        # A comma with one or two digits behind it is a decimal point. More than that
        # and it was separating thousands.
        whole, _, frac = text.rpartition(",")
        text = f"{whole}.{frac}" if len(frac) <= 2 else text.replace(",", "")

    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise ExtractionError(f"{field}: cannot read {raw!r} as a number") from exc


def to_date(raw: object, *, field: str = "date") -> date:
    text = clean(raw)
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ExtractionError(f"{field}: cannot read {raw!r} as a date")


def _address(raw: dict) -> Address:
    return Address(
        name=clean(raw.get("name")),
        street=clean(raw.get("street")),
        zip_code=clean(raw.get("zip_code")),
        city=clean(raw.get("city")),
        country=clean(raw.get("country")),
    )


def _line_item(raw: dict, fallback_position: int) -> LineItem:
    sku = clean(raw.get("sku"))
    return LineItem(
        position=int(raw.get("position") or fallback_position),
        sku=sku,
        description=clean(raw.get("description")),
        quantity=to_decimal(raw.get("quantity"), field=f"{sku} quantity"),
        unit=clean(raw.get("unit")),
        unit_net=to_decimal(raw.get("unit_net"), field=f"{sku} unit_net"),
        discount_percent=to_decimal(raw.get("discount_percent") or "0",
                                    field=f"{sku} discount"),
        vat_percent=to_decimal(raw.get("vat_percent"), field=f"{sku} vat"),
        line_net=to_decimal(raw.get("line_net"), field=f"{sku} line_net"),
    )


def _payment(raw: dict) -> Payment:
    is_paid = bool(raw.get("is_paid"))
    paid_on_raw = clean(raw.get("paid_on"))
    if is_paid and not paid_on_raw:
        raise ExtractionError("document is marked paid but carries no payment date")
    return Payment(
        method=clean(raw.get("method")),
        is_paid=is_paid,
        # Deliberately dropped when unpaid. The brief is explicit that we do not invent
        # a date, and carrying a stray one would leak into the Invoice.
        paid_on=to_date(paid_on_raw, field="payment date") if is_paid else None,
    )


def _debtor(raw: dict) -> Debtor:
    contact = raw.get("contact") or {}
    return Debtor(
        company=clean(raw.get("company")),
        alias=clean(raw.get("alias")),
        customer_id=clean(raw.get("customer_id")),
        contact=Contact(
            first_name=clean(contact.get("first_name")),
            last_name=clean(contact.get("last_name")),
            email=clean(contact.get("email")),
            phone=clean(contact.get("phone")),
        ),
        billing=_address(raw.get("billing") or {}),
        delivery=_address(raw.get("delivery") or {}),
    )


def to_order_data(raw: dict) -> OrderData:
    items = raw.get("items") or []
    if not items:
        raise ExtractionError("no item rows were extracted")

    return OrderData(
        external_reference=clean(raw.get("external_reference")),
        order_date=to_date(raw.get("order_date"), field="order date"),
        currency=clean(raw.get("currency")),
        debtor=_debtor(raw.get("debtor") or {}),
        payment=_payment(raw.get("payment") or {}),
        items=tuple(_line_item(item, i) for i, item in enumerate(items, start=1)),
        net_total=to_decimal(raw.get("net_total"), field="net total"),
        vat_total=to_decimal(raw.get("vat_total"), field="vat total"),
        gross_total=to_decimal(raw.get("gross_total"), field="gross total"),
    )
