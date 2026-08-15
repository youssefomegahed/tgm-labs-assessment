"""Finding controls, and waiting for them to turn up.

Generic Windows plumbing. Nothing here knows what Fakturama is.

What the spike found, which shapes all of this: SWT copies a field's label into the
accessible name, so `Edit name='Working Directory'` is directly addressable and the
usual dance of finding a label and hopping to the field beside it is mostly
unnecessary. Automation ids are present but are numeric handles that change between
sessions, so they are deliberately never used as a key. Control type plus name is what
stays put.
"""

import time

from src.errors import ControlNotFound

# The guest is emulating x64 and SWT repaints lazily, so waits are generous. A too-short
# timeout here shows up as a flaky run that is painful to diagnose.
DEFAULT_TIMEOUT = 20.0
POLL_INTERVAL = 0.3


def _text(value: str | None) -> str:
    return (value or "").strip()


def matches(element, control_type=None, name=None, contains=None, class_name=None) -> bool:
    info = element.element_info

    if control_type and info.control_type != control_type:
        return False
    if class_name and _text(info.class_name) != class_name:
        return False
    if name is not None and _text(info.name) != name:
        return False
    if contains is not None and contains.casefold() not in _text(info.name).casefold():
        return False
    return True


MAX_DEPTH = 16


def iter_descendants(root, max_depth: int = MAX_DEPTH):
    """Breadth-first walk of the tree below `root`, bounded by depth.

    Deliberately not pywinauto's own `descendants()`. That call hangs for minutes on
    Fakturama's main window, while walking the same tree with `children()` covers all
    of it in well under a second. Going level by level also means a locator finds a
    shallow match without paying for the deep subtrees, which matters because the item
    table underneath an Order editor is where most of the nodes live.
    """
    level, depth = [root], 0
    while level and depth < max_depth:
        following = []
        for node in level:
            try:
                children = node.children()
            except Exception:
                continue
            for child in children:
                yield child
                following.append(child)
        level, depth = following, depth + 1


def find_all(root, control_type=None, name=None, contains=None, class_name=None,
             max_depth: int = MAX_DEPTH) -> list:
    """Every matching descendant, right now, without waiting."""
    return [
        element
        for element in iter_descendants(root, max_depth)
        if matches(element, control_type, name, contains, class_name)
    ]


def find_optional(root, timeout: float = DEFAULT_TIMEOUT, **criteria):
    """The single match, or None once the timeout runs out."""
    deadline = time.monotonic() + timeout
    while True:
        found = find_all(root, **criteria)
        if len(found) == 1:
            return found[0]
        if len(found) > 1:
            # Ambiguity is a locator bug, not a data problem, so it is worth being loud
            # rather than quietly taking the first one.
            raise ControlNotFound(
                f"{len(found)} controls match {criteria}, the locator is not specific enough"
            )
        if time.monotonic() >= deadline:
            return None
        time.sleep(POLL_INTERVAL)


def find(root, timeout: float = DEFAULT_TIMEOUT, **criteria):
    element = find_optional(root, timeout=timeout, **criteria)
    if element is None:
        raise ControlNotFound(f"no control matching {criteria} after {timeout:.0f}s")
    return element


def labelled_all(root, label: str, control_type: str = "Edit", max_gap: int = 900,
                 timeout: float = DEFAULT_TIMEOUT) -> list:
    """Every control of `control_type` on the same row as a label, left to right.

    SWT copies most field labels into the field's accessible name, but not all of them.
    Two shapes need this. A single anonymous field beside its label, like Date in the
    Order editor. And one label heading several fields: "ZIP - City" sits in front of a
    ZIP box and a City box, and "First Name Last Name" in front of two more. In both
    cases reading order settles which is which, the same way the eye does.
    """
    anchor = find(root, control_type="Text", name=label, timeout=timeout)
    box = anchor.rectangle()
    middle = (box.top + box.bottom) / 2

    on_the_row = []
    for element in iter_descendants(root):
        if element.element_info.control_type != control_type:
            continue
        rect = element.rectangle()
        if not (rect.top <= middle <= rect.bottom):
            continue
        gap = rect.left - box.right
        if 0 <= gap <= max_gap:
            on_the_row.append((rect.left, element))

    return [element for _, element in sorted(on_the_row, key=lambda pair: pair[0])]


def labelled(root, label: str, control_type: str = "Edit", index: int = 0,
             max_gap: int = 900, timeout: float = DEFAULT_TIMEOUT):
    """The control a label points at, or the `index`-th of several."""
    found = labelled_all(root, label, control_type, max_gap, timeout)
    if len(found) <= index:
        raise ControlNotFound(
            f"wanted {control_type} #{index} beside {label!r}, found {len(found)}"
        )
    return found[index]


def stacked_icons(root, anchor_label: str, control_type: str = "Image",
                  timeout: float = DEFAULT_TIMEOUT) -> list:
    """Un-named icons sitting in a column, ordered top to bottom.

    The brief's sharpest trap is beside Addresses: the upper icon opens the
    existing-contact selector and the lower green plus starts a new Debtor. Neither
    carries a name, so neither can be found by property. They are, however, a tidy
    vertical stack in one column, which orders them unambiguously.

    Sorting by position is not the same as hardcoding a position. The coordinates are
    read off the live window every time, so the rule survives the form moving or the
    window being resized. Only the ordering is assumed.
    """
    anchor = find(root, control_type="Text", name=anchor_label, timeout=timeout)
    box = anchor.rectangle()

    icons = []
    for element in iter_descendants(root):
        if element.element_info.control_type != control_type:
            continue
        if (element.element_info.name or "").strip():
            continue
        rect = element.rectangle()
        # Below the label, and starting no further left than it: the column the label
        # heads, rather than icons belonging to some other part of the form.
        if rect.top >= box.top and rect.left >= box.left - 20 and rect.left <= box.left + 200:
            icons.append((rect.top, element))

    return [element for _, element in sorted(icons, key=lambda pair: pair[0])]


def wait_until(predicate, timeout: float = DEFAULT_TIMEOUT, description: str = "condition"):
    """Poll until the predicate returns something truthy, and hand that back."""
    deadline = time.monotonic() + timeout
    while True:
        try:
            result = predicate()
            if result:
                return result
        except Exception:
            # Controls come and go while a dialog is building itself.
            result = None
        if time.monotonic() >= deadline:
            raise ControlNotFound(f"timed out after {timeout:.0f}s waiting for {description}")
        time.sleep(POLL_INTERVAL)


def wait_stable(read, timeout: float = DEFAULT_TIMEOUT, settle: int = 3):
    """Wait for a value to stop changing, then return it.

    This is what the brief means by "wait for the list to stabilize". A search box that
    filters as you type goes through several intermediate results, and grabbing the
    first non-empty one reads a half-filtered list. Requiring the same answer several
    polls running is what makes that safe.
    """
    deadline = time.monotonic() + timeout
    previous, repeats = object(), 0

    while True:
        current = read()
        repeats = repeats + 1 if current == previous else 0
        previous = current

        if repeats >= settle - 1:
            return current
        if time.monotonic() >= deadline:
            raise ControlNotFound(f"value never settled within {timeout:.0f}s")
        time.sleep(POLL_INTERVAL)
