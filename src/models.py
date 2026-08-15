"""The shape of one order, as read off the source document.

Everything downstream works on these types. Nothing here knows about Gemini or about
Fakturama, so the extraction side and the UI side can be built and tested apart.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from src.money import money


@dataclass(frozen=True)
class Address:
    """One address block. `name` is whatever heads the block, which is not always the
    company: the delivery block on our sample reads "Northstar Office Warehouse"."""

    name: str
    street: str
    zip_code: str
    city: str
    country: str

    def same_place_as(self, other: "Address") -> bool:
        return (
            self.name == other.name
            and self.street == other.street
            and self.zip_code == other.zip_code
            and self.city == other.city
            and self.country == other.country
        )


@dataclass(frozen=True)
class Contact:
    first_name: str
    last_name: str
    email: str
    phone: str


@dataclass(frozen=True)
class Debtor:
    company: str
    alias: str
    customer_id: str  # the reference printed on the source, not Fakturama's own id
    contact: Contact
    billing: Address
    delivery: Address

    @property
    def delivery_is_billing(self) -> bool:
        """Drives whether the Debtor needs a second address in Fakturama. When the two
        blocks are the same the Main address carries both roles."""
        return self.billing.same_place_as(self.delivery)


@dataclass(frozen=True)
class LineItem:
    position: int
    sku: str
    description: str
    quantity: Decimal
    unit: str
    unit_net: Decimal
    discount_percent: Decimal
    vat_percent: Decimal
    line_net: Decimal  # as printed, kept so validation has something to check against

    @property
    def computed_net(self) -> Decimal:
        """What the line should come to. Compared against `line_net` in validation."""
        factor = 1 - self.discount_percent / 100
        return money(self.quantity * self.unit_net * factor)

    @property
    def master_gross_price(self) -> Decimal:
        """Price (gross) for the Product master record.

        The line discount deliberately does not apply here. It belongs to this
        transaction, not to the product, which is why the brief calls it out.
        """
        return money(self.unit_net * (1 + self.vat_percent / 100))

    @property
    def vat_rate_name(self) -> str:
        """Fakturama names VAT rates "VAT 19%". Trailing zeros would not match, so 19.0
        has to render as 19."""
        percent = self.vat_percent.normalize()
        return f"VAT {percent:f}%"


@dataclass(frozen=True)
class Payment:
    method: str
    is_paid: bool
    paid_on: date | None  # only set when is_paid, never invented


@dataclass(frozen=True)
class OrderData:
    external_reference: str
    order_date: date
    currency: str
    debtor: Debtor
    payment: Payment
    items: tuple[LineItem, ...]
    net_total: Decimal
    vat_total: Decimal
    gross_total: Decimal

    @property
    def vat_rate_names(self) -> list[str]:
        """Distinct VAT rates the order needs, in first-seen order."""
        seen = {}
        for item in self.items:
            seen.setdefault(item.vat_rate_name, None)
        return list(seen)
