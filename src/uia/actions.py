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


def is_selected(element) -> bool:
    try:
        return bool(element.is_selected())
    except Exception:
        return False


def display_scale() -> float:
    """How many physical pixels there are per logical one, e.g. 2.0 at 200%."""
    import ctypes

    hdc = ctypes.windll.user32.GetDC(0)
    try:
        dpi = ctypes.windll.gdi32.GetDeviceCaps(hdc, 88)  # LOGPIXELSX
    finally:
        ctypes.windll.user32.ReleaseDC(0, hdc)
    return (dpi or 96) / 96.0


def select_tab(element, *, what: str = "tab") -> None:
    """Switch to a tab, and make sure it actually switched.

    Two problems stack up here.

    Both invoke and select report success on SWT's tab items without changing the page,
    which is the worst kind of failure: the caller then hunts for controls that were
    never realized. So the selection state is checked afterwards rather than assumed,
    which is the read-back rule applied to navigation instead of to a value.

    And SWT reports tab item rectangles in logical coordinates while reporting every
    other control in physical ones. On a scaled display that puts the rectangle at a
    fraction of where the tab really is, so a plain click lands somewhere else
    entirely. Scaling the rectangle back up is what makes the click land.
    """
    if is_selected(element):
        return

    try:
        element.select()
        time.sleep(0.8)
        if is_selected(element):
            return
    except Exception:
        pass

    rect = element.rectangle()
    scale = display_scale()
    point = (int((rect.left + rect.width() / 2) * scale),
             int((rect.top + rect.height() / 2) * scale))

    from pywinauto import mouse

    mouse.click(coords=point)
    time.sleep(0.8)

    if not is_selected(element):
        raise VerificationFailed(f"{what} tab", "selected",
                                 f"not selected after clicking {point}")


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


def combo_items(element) -> list[str]:
    """The options a dropdown offers, by expanding it and reading the list."""
    try:
        element.expand()
        time.sleep(SETTLE)
        names = [
            (item.element_info.name or "").strip()
            for item in element.descendants(control_type="ListItem")
        ]
        element.collapse()
        return [name for name in names if name]
    except Exception:
        return []


def _open_list(element) -> bool:
    """Open a dropdown's list, whichever way this one supports.

    Fakturama's combos do not all implement ExpandCollapse. Several carry a child button
    named "Open" instead, and for those `expand()` raises, which previously got swallowed
    so the retry loop spun on a no-op three times and reported the value had not changed.
    """
    try:
        element.expand()
        time.sleep(SETTLE)
        return True
    except Exception:
        pass

    for child in element.children():
        if (child.element_info.name or "").strip() == "Open":
            child.click_input()
            time.sleep(SETTLE * 2)
            return True
    return False


def _pick_from_open_list(element, value: str) -> None:
    """Choose `value` from an opened list.

    Clicking a matching ListItem only works when that item is realized, and a country
    list of a couple of hundred entries is virtualized, so most of them are not. Typing
    into an *open* list is the reliable route: it runs the widget's own incremental
    search and Enter commits it.

    Typing into a *closed* combo is a different thing entirely and is not safe here.
    It prefix-matches per keystroke and walks the selection, which is how "Credit
    transfer" once landed on "Standing agreement".
    """
    if not _open_list(element):
        raise LookupError("could not open the dropdown")

    for item in element.descendants(control_type="ListItem"):
        if (item.element_info.name or "").strip() == value:
            try:
                item.select()
            except Exception:
                item.click_input()
            time.sleep(SETTLE)
            return

    element.type_keys(str(value), with_spaces=True, pause=0.03)
    time.sleep(SETTLE)
    element.type_keys("{ENTER}")
    time.sleep(SETTLE)


def select_combo(element, value: str, *, attempts: int = 3,
                 what: str = "dropdown") -> None:
    """Pick an option by its exact text.

    Typing the value is not a safe fallback here. An SWT combo prefix-matches on every
    keystroke, so typing "Credit transfer" walks through several entries and can settle
    on a different one: this landed on "Standing agreement" before the read-back caught
    it. Expanding the list and clicking the matching item is the reliable route.

    Retried, because a combo on a page SWT has only just built sometimes ignores the
    first attempt and keeps its default. That showed up on the Country dropdown of a
    second address added moments earlier, where the identical call had worked on the
    first address.
    """
    for attempt in range(attempts):
        if attempt:
            time.sleep(0.6 * attempt)

        # Raise the owning window first. A dropdown cannot render its list if something
        # is covering the control, and the thing covering it is usually the console the
        # automation is being driven from. Writes through the value pattern are immune to
        # this, so the symptom is text fields working while a combo silently keeps its
        # default.
        try:
            element.set_focus()
            time.sleep(SETTLE)
        except Exception:
            pass

        try:
            element.select(value)
            time.sleep(SETTLE)
            if read_value(element).strip() == value:
                return
        except Exception:
            pass

        try:
            _pick_from_open_list(element, value)
        except VerificationFailed:
            raise
        except Exception:
            pass

        if read_value(element).strip() == value:
            return

    raise VerificationFailed(what, value, read_value(element).strip())
