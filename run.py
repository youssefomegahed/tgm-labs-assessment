"""Entry point: one order image through to a saved, verified Invoice.

    python run.py data/order.png --dry-run    read and check the image only
    python run.py data/order.png              drive Fakturama as well
"""

import argparse
import json
import sys

from src.errors import AutomationError, ManualReviewRequired
from src.extract.client import extract_order
from src.extract.normalize import to_order_data
from src.extract.validate import assert_consistent
from src.models import OrderData


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("image", help="the order image to read")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="extract and validate only, leave Fakturama alone",
    )
    parser.add_argument("--out", help="write the raw extraction to this json file")
    parser.add_argument(
        "--extraction",
        metavar="JSON",
        help="load a previous extraction instead of calling the model, so the "
        "Fakturama stages can be worked on without spending API calls",
    )
    return parser.parse_args(argv)


def summarise(order: OrderData) -> str:
    lines = [
        f"reference   {order.external_reference}",
        f"date        {order.order_date}",
        f"debtor      {order.debtor.company} ({order.debtor.alias})",
        f"contact     {order.debtor.contact.first_name} "
        f"{order.debtor.contact.last_name}",
        f"billing     {order.debtor.billing.street}, "
        f"{order.debtor.billing.zip_code} {order.debtor.billing.city}",
        f"delivery    {order.debtor.delivery.name}, "
        f"{order.debtor.delivery.street}, "
        f"{order.debtor.delivery.zip_code} {order.debtor.delivery.city}",
        f"payment     {order.payment.method}"
        + (f", paid {order.payment.paid_on}" if order.payment.is_paid else ", unpaid"),
        "items",
    ]
    for item in order.items:
        lines.append(
            f"  {item.position}. {item.sku:<12} {item.description:<24} "
            f"{item.quantity} x {item.unit_net} less {item.discount_percent}% "
            f"@ {item.vat_percent}% = {item.line_net}"
        )
    lines.append(
        f"totals      net {order.net_total}, vat {order.vat_total}, "
        f"gross {order.gross_total} {order.currency}"
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if args.extraction:
        with open(args.extraction) as handle:
            raw = json.load(handle)
        print(f"using extraction from {args.extraction}, model not called\n")
    else:
        raw = extract_order(args.image)

    if args.out:
        with open(args.out, "w") as handle:
            json.dump(raw, handle, indent=2)
        print(f"wrote {args.out}")

    order = to_order_data(raw)
    print(summarise(order))

    print("\nchecks")
    for check in assert_consistent(order):
        print(f"  {check}")

    if args.dry_run:
        print("\ndry run, stopping before Fakturama")
        return 0

    # The UI stages land next. Until then, be honest about it rather than pretending.
    print("\nthe Fakturama stages are not wired up yet, use --dry-run")
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ManualReviewRequired as stop:
        print(f"\nstopped for manual review: {stop}", file=sys.stderr)
        sys.exit(2)
    except AutomationError as error:
        print(f"\nfailed: {error}", file=sys.stderr)
        sys.exit(1)
