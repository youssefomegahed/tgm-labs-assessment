"""Getting hold of the Fakturama window.

The one piece of app-specific knowledge allowed in this layer is where the executable
lives and what its windows are called. Everything else about Fakturama belongs a layer
up.
"""

import ctypes
import os
import subprocess
import sys
import time

from pywinauto import Desktop

from src.errors import ControlNotFound
from src.uia.locator import DEFAULT_TIMEOUT, wait_until

EXECUTABLE = os.environ.get(
    "FAKTURAMA_EXE", r"C:\Program Files\Fakturama2\Fakturama.exe"
)

# SWT shells all use this class, which is a more reliable handle than the title: the
# title changes as the app moves between its init dialog and its main window.
SHELL_CLASS = "SWT_Window0"

# Fakturama raises simple alerts as native Win32 message boxes rather than SWT shells,
# and those carry the standard dialog class. They are also owned windows, so a plain
# top-level enumeration does not see them at all.
MESSAGE_BOX_CLASS = "#32770"

_dpi_ready = False


def ensure_dpi_aware() -> None:
    """Must run before anything reads a coordinate.

    On a scaled desktop a process that has not declared itself DPI aware sees logical
    pixels while the framebuffer is physical. Clicks then land in the wrong place and
    screenshots come out cropped, both of which look like mysterious flakiness rather
    than a configuration problem.
    """
    global _dpi_ready
    if _dpi_ready or sys.platform != "win32":
        return
    ctypes.windll.user32.SetProcessDPIAware()
    _dpi_ready = True


def desktop() -> Desktop:
    ensure_dpi_aware()
    return Desktop(backend="uia")


def _windows_of_class(prefix: str) -> list:
    """Top-level windows whose class name starts with `prefix`.

    This goes through Win32 EnumWindows rather than pywinauto's own enumeration on
    purpose. Owned windows, which is what Fakturama's alerts are, only show up in
    pywinauto with top_level_only off, and that walks the entire UIA tree of every
    window on the desktop. On Fakturama's main window that takes minutes. EnumWindows
    already returns owned windows and costs nothing.
    """
    import win32gui

    handles: list[int] = []

    def collect(handle, _):
        try:
            if win32gui.IsWindowVisible(handle) and \
                    win32gui.GetClassName(handle).startswith(prefix):
                handles.append(handle)
        except Exception:
            pass
        return True

    win32gui.EnumWindows(collect, None)

    found = []
    for handle in handles:
        try:
            found.append(desktop().window(handle=handle).wrapper_object())
        except Exception:
            continue
    return found


def shells() -> list:
    """Every SWT top-level window currently open."""
    return _windows_of_class(SHELL_CLASS)


def find_shell(title_contains: str = "", timeout: float = DEFAULT_TIMEOUT):
    """Wait for an SWT window whose title contains the given text."""
    wanted = title_contains.casefold()

    def look():
        for window in shells():
            title = (window.window_text() or "").casefold()
            if wanted in title:
                return window
        return None

    return wait_until(look, timeout=timeout, description=f"window matching {title_contains!r}")


def message_boxes() -> list:
    """Native alert dialogs currently on screen."""
    return _windows_of_class(MESSAGE_BOX_CLASS)


def find_dialog(title_contains: str = "", timeout: float = DEFAULT_TIMEOUT):
    """Wait for a native dialog with a matching title.

    Fakturama's selector dialogs, "Select the address" and "Select a product", use the
    same native class as its alerts and host SWT panes inside it.
    """
    wanted = title_contains.casefold()

    def look():
        for window in message_boxes():
            if wanted in (window.window_text() or "").casefold():
                return window
        return None

    return wait_until(look, timeout=timeout, description=f"dialog {title_contains!r}")


def find_message_box(title_contains: str = "", timeout: float = DEFAULT_TIMEOUT):
    return find_dialog(title_contains, timeout)


def dismiss_message_box(title_contains: str = "", button: str = "OK",
                        timeout: float = DEFAULT_TIMEOUT) -> str:
    """Acknowledge an alert and return what it said, so callers can log it."""
    from src.uia import actions
    from src.uia.locator import find

    box = find_message_box(title_contains, timeout=timeout)
    message = " ".join(
        (child.window_text() or "").strip()
        for child in box.descendants(control_type="Text")
    ).strip()

    actions.click(find(box, control_type="Button", name=button, timeout=5))
    return message


def clear_message_boxes(limit: int = 5) -> list[str]:
    """Dismiss any alert already on screen, and say what they were.

    Worth doing before a flow starts. A message box left over from an earlier run is an
    owned child of the main window, so its buttons show up in searches rooted there and
    make otherwise specific locators ambiguous.
    """
    dismissed = []
    for _ in range(limit):
        if not message_boxes():
            break
        try:
            dismissed.append(dismiss_message_box(timeout=3))
        except Exception:
            break
    return dismissed


def is_running() -> bool:
    return bool(shells())


def launch(timeout: float = 180.0):
    """Start Fakturama if it is not already up, and hand back its window.

    Eclipse RCP starting under x64 emulation is slow enough that the default timeout is
    measured in minutes rather than seconds.
    """
    if not is_running():
        subprocess.Popen([EXECUTABLE])
        time.sleep(5)

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        windows = shells()
        if windows:
            return windows[0]
        time.sleep(1.0)

    raise ControlNotFound(f"Fakturama did not open a window within {timeout:.0f}s")
