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

    return drive_fakturama(order)


def drive_fakturama(order: OrderData) -> int:
    """Run the brief's stages against a live Fakturama.

    Imported here rather than at module scope so that --dry-run, and the tests, work on
    a machine without pywinauto.
    """
    from src.fakturama.main_window import MainWindow
    from src.flow import debtor as debtor_flow
    from src.flow import order as order_flow

    def step(message: str) -> None:
        print(f"  {message}")

    main_window = MainWindow.launch()

    print("\nstage 1: open the Order")
    order_flow.begin(main_window, order, log=step)

    print("\nstage 2: select or create the Debtor")
    debtor_flow.resolve(main_window, order, log=step)

    # Stages 3 to 5 land next: Products and VAT, saving the Order, the linked Invoice.
    print("\nstages 1 and 2 complete. Products, Order save and Invoice are not built yet.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ManualReviewRequired as stop:
        print(f"\nstopped for manual review: {stop}", file=sys.stderr)
        sys.exit(2)
    except AutomationError as error:
        print(f"\nfailed: {error}", file=sys.stderr)
        sys.exit(1)
