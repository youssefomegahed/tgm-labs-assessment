"""Does the extraction add up?

This is the confidence check on a low resolution image. The model transcribed the
printed figures without calculating anything, so recomputing them here compares two
independent readings. A misread digit almost always breaks one of these, which is
cheaper and more reliable than running a second OCR pass and diffing the text.
"""

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

from src.errors import ManualReviewRequired
from src.models import OrderData
from src.money import money


@dataclass(frozen=True)
class Check:
    name: str
    computed: Decimal  # what the numbers come to
    printed: Decimal  # what the document claims

    @property
    def ok(self) -> bool:
        return self.computed == self.printed

    @property
    def delta(self) -> Decimal:
        return self.printed - self.computed

    def __str__(self) -> str:
        mark = "ok  " if self.ok else "FAIL"
        detail = "" if self.ok else f"  (off by {self.delta:+})"
        return f"{mark} {self.name}: computed {self.computed}, printed {self.printed}{detail}"


def check_order(order: OrderData) -> list[Check]:
    """Every arithmetic claim the document makes, checked."""
    checks = [
        Check(f"line {item.position} ({item.sku})", item.computed_net, item.line_net)
        for item in order.items
    ]

    checks.append(Check(
        "net total",
        money(sum(item.line_net for item in order.items)),
        order.net_total,
    ))
    checks.append(Check("vat total", _vat_across_rates(order), order.vat_total))
    checks.append(Check(
        "gross total",
        money(order.net_total + order.vat_total),
        order.gross_total,
    ))
    return checks


def _vat_across_rates(order: OrderData) -> Decimal:
    """VAT is rounded once per rate, not once per line.

    Our sample is single rate so it makes no difference, but summing per-line rounded
    VAT drifts by a cent or two on mixed-rate orders, which would then read as a
    genuine mismatch.
    """
    net_by_rate: dict[Decimal, Decimal] = defaultdict(Decimal)
    for item in order.items:
        net_by_rate[item.vat_percent] += item.line_net

    return money(sum(money(net * rate / 100) for rate, net in net_by_rate.items()))


def assert_consistent(order: OrderData) -> list[Check]:
    """Run the checks and stop the flow if any fail.

    A document whose own totals do not add up is exactly the case the brief means by
    stop for manual review. Pushing it into Fakturama would save wrong numbers.
    """
    checks = check_order(order)
    failed = [check for check in checks if not check.ok]
    if failed:
        raise ManualReviewRequired(
            "extracted figures do not add up:\n  "
            + "\n  ".join(str(check) for check in failed),
            stage="extraction",
        )
    return checks
