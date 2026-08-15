"""Dev tool: look at what Fakturama actually exposes to UIA.

Run this in the guest before writing any locators. It answers the one question the
design could not settle by reasoning: how much of the UI is reachable by properties,
and how much needs the vision fallback.

    C:\\dev\\venv\\Scripts\\python.exe tools\\spike_uia.py windows
    C:\\dev\\venv\\Scripts\\python.exe tools\\spike_uia.py tree --depth 3
    C:\\dev\\venv\\Scripts\\python.exe tools\\spike_uia.py shot runs\\screen.png
"""

import argparse
import ctypes
import sys
import time

# Before importing anything that measures the screen. Without this, a scaled desktop
# reports logical pixels while the framebuffer is physical, and every coordinate and
# screenshot comes out wrong.
if sys.platform == "win32":
    ctypes.windll.user32.SetProcessDPIAware()

from pywinauto import Desktop  # noqa: E402

FAKTURAMA = "Fakturama"


def list_windows() -> int:
    for window in Desktop(backend="uia").windows():
        try:
            rect = window.rectangle()
            print(f"{window.class_name():<28} {str(rect):<32} {window.window_text()!r}")
        except Exception as exc:  # a window can die between enumerating and reading it
            print(f"  (unreadable: {exc})")
    return 0


def find_fakturama():
    """The main window, however it happens to be titled today."""
    for window in Desktop(backend="uia").windows():
        try:
            if FAKTURAMA.lower() in (window.window_text() or "").lower():
                return window
            if "SWT_Window" in (window.class_name() or ""):
                return window
        except Exception:
            continue
    return None


def describe(element, indent: int) -> str:
    """One line per control: what it is, what it is called, where it is.

    automation_id is the prize. Where SWT sets one, a locator can key off it and stop
    caring about labels or position entirely.
    """
    info = element.element_info
    parts = [f"{'  ' * indent}{info.control_type or '?'}"]

    name = (info.name or "").strip()
    if name:
        parts.append(f"name={name[:48]!r}")

    auto_id = (info.automation_id or "").strip()
    if auto_id:
        parts.append(f"id={auto_id!r}")

    class_name = (info.class_name or "").strip()
    if class_name:
        parts.append(f"class={class_name}")

    rect = element.rectangle()
    parts.append(f"@({rect.left},{rect.top} {rect.width()}x{rect.height()})")
    return "  ".join(parts)


def walk(element, depth: int, indent: int = 0, counts: dict | None = None) -> None:
    if counts is not None:
        control_type = element.element_info.control_type or "?"
        counts[control_type] = counts.get(control_type, 0) + 1
        if (element.element_info.automation_id or "").strip():
            counts["_with_automation_id"] = counts.get("_with_automation_id", 0) + 1
        if (element.element_info.name or "").strip():
            counts["_with_name"] = counts.get("_with_name", 0) + 1

    print(describe(element, indent))
    if indent >= depth:
        return

    try:
        children = element.children()
    except Exception as exc:
        print(f"{'  ' * (indent + 1)}(children unreadable: {exc})")
        return

    for child in children:
        walk(child, depth, indent + 1, counts)


def dump_tree(depth: int) -> int:
    window = find_fakturama()
    if window is None:
        print("no Fakturama window found, is it still starting?")
        return 1

    print(f"main window: {window.window_text()!r} {window.rectangle()}\n")
    counts: dict = {}
    walk(window, depth, counts=counts)

    print("\n--- summary ---")
    named = counts.pop("_with_name", 0)
    with_id = counts.pop("_with_automation_id", 0)
    total = sum(counts.values())
    for control_type, count in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {count:>4}  {control_type}")
    print(f"\n  {total} controls, {named} with a name, {with_id} with an automation id")
    return 0


def screenshot(path: str) -> int:
    """Grab the framebuffer, not the window.

    capture_as_image() goes through PrintWindow, and SWT draws through Java in a way
    that comes back as a black rectangle. Reading the actual screen sidesteps that, at
    the cost of having to raise the window first.
    """
    from PIL import ImageGrab

    window = find_fakturama()
    if window is not None:
        try:
            window.set_focus()
            time.sleep(1.5)  # SWT repaints lazily, and this VM is emulating x64
        except Exception as exc:
            print(f"could not raise the window: {exc}")

    image = ImageGrab.grab(all_screens=True)
    image.save(path)
    print(f"saved {image.width}x{image.height} -> {path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("windows", help="list every top-level window")

    tree = sub.add_parser("tree", help="dump the Fakturama control tree")
    tree.add_argument("--depth", type=int, default=2)

    shot = sub.add_parser("shot", help="screenshot the Fakturama window")
    shot.add_argument("path")

    args = parser.parse_args()
    if args.command == "windows":
        return list_windows()
    if args.command == "tree":
        return dump_tree(args.depth)
    return screenshot(args.path)


if __name__ == "__main__":
    sys.exit(main())
