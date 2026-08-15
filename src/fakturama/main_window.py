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
        # vision layer reads tables from screenshots of these regions.
        session.minimize_consoles()
        self.window.set_focus()

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

    def save(self) -> None:
        """The toolbar Save, which the brief is careful to say is clicked exactly once."""
        self.click_toolbar("save")
