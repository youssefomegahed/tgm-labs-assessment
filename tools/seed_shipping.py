"""Create the default Shipping record a New Order needs.

Fakturama refuses to open a New Order with "No default value found for Shippings", and
that record is seed data created by the first-run wizard. Anyone who resets by deleting
the workspace folder loses it, because Fakturama remembers the workspace path elsewhere
and rebuilds the database without re-running the wizard.

The brief wants shipping at "Free of shipping costs / 0.00" anyway, so this creates
exactly that and marks it standard.

    C:\\dev\\venv\\Scripts\\python.exe tools\\seed_shipping.py
"""

import sys
import time

from src.fakturama.main_window import MainWindow
from src.uia import actions, session
from src.uia.locator import find, find_all, find_optional

NAME = "Free of shipping costs"


def main() -> int:
    session.ensure_dpi_aware()
    main_window = MainWindow.launch()
    main_window.focus()
    time.sleep(1)

    for message in session.clear_message_boxes():
        print(f"dismissed: {message!r}")

    main_window.open_navigation("Shippings")
    create = find(main_window.window, control_type="Button",
                  contains="Create a new shipping", timeout=45)
    print("Shippings view open")

    actions.click(create)
    time.sleep(5)

    actions.set_text(find(main_window.window, control_type="Edit", name="Name"),
                     NAME, what="shipping Name")
    description = find_optional(main_window.window, control_type="Edit",
                                name="Description", timeout=5)
    if description is not None:
        actions.set_text(description, NAME, what="shipping Description")

    for label in ("Shipping value", "Value", "Shipping"):
        field = find_optional(main_window.window, control_type="Edit", name=label,
                              timeout=3)
        if field is not None:
            actions.set_text(field, "0.00", what=label)
            print(f"set {label} to 0.00")
            break

    # Without a standard, Fakturama still refuses to open an Order.
    standard = find_optional(main_window.window, control_type="Button",
                             name="Set as standard", timeout=5)
    if standard is not None:
        actions.click(standard)
        print("marked as standard")

    main_window.save()
    time.sleep(4)

    names = [
        (element.element_info.name or "")
        for element in find_all(main_window.window, control_type="TabItem")
    ]
    print(f"open tabs after save: {[n for n in names if n]}")
    print("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
