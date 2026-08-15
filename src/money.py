"""Money rounding, in one place so every total agrees with every other total.

Decimal defaults to banker's rounding, which is not what an invoice does. A line at
x.xx5 has to round up the way the printed document rounds it, otherwise our computed
totals drift from the source by a cent and the validation fires on a false alarm.
"""

from decimal import Decimal, ROUND_HALF_UP

CENTS = Decimal("0.01")


def money(value: Decimal | str | int) -> Decimal:
    """Round to two decimal places the way an invoice does."""
    return Decimal(value).quantize(CENTS, rounding=ROUND_HALF_UP)
