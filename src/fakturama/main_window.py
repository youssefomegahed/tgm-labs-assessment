"""The Fakturama application window: toolbar and the left navigation panel.

Every locator for these lives here so the flow can say what it wants rather than how to
find it.
"""

from src.uia import actions, session
from src.uia.locator import find

# Toolbar buttons are named after their tooltip rather than their caption, which is why
# these read as sentences.
TOOLBAR = {
    "order": "Create: New Order",
    "invoice": "Create: New Invoice",
    "delivery": "Create: New Delivery Note",
    "save": "Save the current contents",
    "product": "Create a new product",
}

# The brief's "Data > Documents" is this panel, not the menu bar. The entries are Text
# controls rather than buttons or links, so they need a real click.
NAVIGATION = (
    "Documents", "Products", "Creditors", "Debtors", "terms of payment",
    "Shippings", "VATs", "Texts", "Lists",
    "New product", "New Contact",
)


class MainWindow:
    def __init__(self, window=None):
        self.window = window or session.shells()[0]

    @classmethod
    def launch(cls) -> "MainWindow":
        session.ensure_dpi_aware()
        window = session.launch()
        for message in session.clear_message_boxes():
            print(f"cleared a leftover dialog: {message!r}")
        return cls(window)

    def focus(self) -> None:
        # Nothing may sit over the app: clicks land on whatever covers it, and the
        # vision layer reads tables from screenshots of these regions. The window must
        # also be maximized, for the same reason.
        session.minimize_consoles()
        self.window.set_focus()
        session.ensure_maximized(self.window)
        # Holds for the whole run, unlike minimizing consoles that keep reappearing.
        session.keep_on_top(self.window)

    def click_toolbar(self, key: str) -> None:
        actions.click(find(self.window, control_type="Button", name=TOOLBAR[key]))

    def open_navigation(self, entry: str) -> None:
        """Open one of the left panel entries, such as VATs or terms of payment."""
        if entry not in NAVIGATION:
            raise KeyError(f"{entry!r} is not a navigation entry")
        find(self.window, control_type="Text", name=entry).click_input()

    def focus_editor(self, title_contains: str) -> None:
        """Bring an editor tab to the front.

        Matched on a substring because an editor with unsaved changes shows a leading
        asterisk: the Order tab is "New Order" until it is touched and "*New Order"
        afterwards. The brief leans on this repeatedly, telling us to keep the Order open
        and come back to it, and to return to the Debtor after creating a payment method.
        """
        actions.select_tab(
            find(self.window, control_type="TabItem", contains=title_contains),
            what=title_contains,
        )

    def open_tab(self, title: str) -> None:
        actions.select_tab(find(self.window, control_type="TabItem", name=title),
                           what=title)

    def has_tab(self, title_contains: str) -> bool:
        from src.uia.locator import find_optional

        return find_optional(self.window, control_type="TabItem",
                             contains=title_contains, timeout=2) is not None

    def maximize_editor_area(self) -> None:
        """Expand the editor stack to the full window.

        The Debtor form is taller than the editor pane, and rows below the pane's edge
        are half-real: value writes reach them, but clicks land on whatever is painted
        there instead, which for the address type picker was the panel boundary. Rather
        than scroll-into-view arithmetic, use Eclipse's own answer: the editor stack has
        a Maximize button, and a maximized stack shows the whole form.
        """
        self._editor_stack_button("Maximize")

    def restore_editor_area(self) -> None:
        """Bring the bottom panel back, which verification reads later."""
        self._editor_stack_button("Restore")

    # The window's own title bar carries Minimize/Maximize/Restore too, and clicking
    # those resizes the whole application rather than the editor stack. They are
    # distinguishable: title bar buttons sit at the very top and are roughly twice as
    # wide as the small pane buttons.
    TITLE_BAR_DEPTH = 120
    PANE_BUTTON_MAX_WIDTH = 60

    def _editor_stack_button(self, name: str) -> None:
        import time

        from src.uia.locator import find_all

        candidates = [
            button for button in find_all(self.window, control_type="Button", name=name)
            if button.rectangle().top > self.TITLE_BAR_DEPTH
            and button.rectangle().width() <= self.PANE_BUTTON_MAX_WIDTH
        ]
        if not candidates:
            return

        # Topmost of the remaining ones is the editor stack; the lower copy belongs to
        # the bottom panel.
        actions.click(min(candidates, key=lambda button: button.rectangle().top))
        time.sleep(1.0)

    def save(self) -> None:
        """The toolbar Save, which the brief is careful to say is clicked exactly once."""
        self.click_toolbar("save")
