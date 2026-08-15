"""Doing things to controls, and checking they took.

Every write reads itself back. Setting a field and moving on assumes the click landed,
the widget had focus and it accepted the value. None of those are free on an SWT form
being driven from outside, and a silent wrong value is the expensive kind of bug: it
ends up saved in an invoice.
"""

import time

from src.errors import VerificationFailed

SETTLE = 0.2  # SWT applies a value on its own event loop, not on the setter's return


def read_value(element) -> str:
    """The value in a field, which is not the same as its accessible name.

    UIA reports an SWT Edit's *label* as its name, so window_text() on the Working
    Directory box gives back "Working Directory" rather than what is typed in it. The
    value pattern is the one that answers the question actually being asked.
    """
    try:
        return (element.get_value() or "").strip()
    except Exception:
        pass

    try:
        return (element.legacy_properties().get("Value") or "").strip()
    except Exception:
        return (element.window_text() or "").strip()


def set_text(element, value: str, *, what: str = "field") -> None:
    element.set_focus()
    try:
        element.set_edit_text(value)
    except Exception:
        # Some SWT widgets refuse the value pattern and only accept real keystrokes.
        element.type_keys("^a{BACKSPACE}", pause=0.02)
        element.type_keys(str(value), with_spaces=True, pause=0.02)

    time.sleep(SETTLE)
    actual = read_value(element)
    if actual != str(value):
        raise VerificationFailed(what, value, actual)


def click(element) -> None:
    """Prefer the invoke pattern, fall back to a real click.

    Invoke is faster and does not care whether the control is on screen. Some SWT
    buttons do not implement it, and those need the mouse.
    """
    try:
        element.invoke()
    except Exception:
        element.click_input()
    time.sleep(SETTLE)


def set_checkbox(element, want: bool, *, what: str = "checkbox") -> None:
    if is_checked(element) == want:
        return

    click(element)
    time.sleep(SETTLE)
    actual = is_checked(element)
    if actual != want:
        raise VerificationFailed(what, want, actual)


def is_checked(element) -> bool:
    try:
        return bool(element.get_toggle_state())
    except Exception:
        return bool(element.legacy_properties().get("State", 0) & 0x10)


def select_combo(element, value: str, *, what: str = "dropdown") -> None:
    """Pick an option by its exact text."""
    try:
        element.select(value)
    except Exception:
        element.set_focus()
        element.type_keys(str(value), with_spaces=True, pause=0.02)

    time.sleep(SETTLE)
    actual = read_value(element) or (element.selected_text() if hasattr(element, "selected_text") else "")
    if actual.strip() != value:
        raise VerificationFailed(what, value, actual)
