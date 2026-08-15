"""One-time setup: get Fakturama past its initialization dialog.

Fakturama asks for a working directory the first time it starts. That is setup rather
than part of the image-to-cash flow, so it lives here instead of in src/flow.

Keeping the data directory at a known path matters for a second reason: resetting
between runs is a matter of restoring a clean copy of it.

    C:\\dev\\venv\\Scripts\\python.exe tools\\first_run.py
"""

import os
import pathlib
import sys
import time

from src.uia import actions, session
from src.uia.locator import find, find_optional

# Overridable, but keeping it at a known path is what makes resetting between runs a
# matter of restoring a copy of one directory.
DATA_DIR = os.environ.get("FAKTURAMA_DATA", r"C:\FakturamaData")


def main() -> int:
    session.ensure_dpi_aware()
    pathlib.Path(DATA_DIR).mkdir(parents=True, exist_ok=True)

    window = session.launch()
    print(f"window: {window.window_text()!r}")

    for message in session.clear_message_boxes():
        print(f"cleared a leftover dialog: {message!r}")

    if "initialization" not in (window.window_text() or "").casefold():
        print("no initialization dialog, Fakturama is already set up")
        return 0

    working_dir = find(window, control_type="Edit", name="Working Directory")
    actions.set_text(working_dir, DATA_DIR, what="Working Directory")
    print(f"working directory: {actions.read_value(working_dir)}")

    defaults = find_optional(
        window, control_type="CheckBox", name="use default database settings", timeout=3
    )
    if defaults is not None:
        actions.set_checkbox(defaults, True, what="use default database settings")
        print(f"default database settings: {actions.is_checked(defaults)}")

    actions.click(find(window, control_type="Button", name="OK"))
    print("clicked OK")

    # Choosing a workspace makes Fakturama restart itself, and it says so in a native
    # message box rather than an SWT dialog.
    message = session.dismiss_message_box("Information", timeout=30)
    print(f"acknowledged: {message!r}")

    print("waiting for Fakturama to restart, this takes a while under emulation")
    main_window = session.find_shell(timeout=300)
    while "initialization" in (main_window.window_text() or "").casefold():
        time.sleep(3)
        main_window = session.find_shell(timeout=300)

    print(f"main window: {main_window.window_text()!r} {main_window.rectangle()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
