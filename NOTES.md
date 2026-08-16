# Findings: how Fakturama's UI behaves under automation

Things about the target application that are not obvious from the outside and are in no
documentation. Most cost real time to find, and several are the kind of thing that would
cost it again, so they are written down as properties of Fakturama rather than as a
record of my afternoon.

The through-line, if there is one: **on this application a write reports success without
the application having accepted it**, and almost every bug here was that same bug wearing
a different hat.

## What SWT does to UIA

Fakturama is Eclipse RCP on SWT. The accessibility tree is much better than I expected in
some places and absent in others.

**Field labels become the field's accessible name.** `Edit 'Cust.Ref.'` is directly
addressable. This is the single biggest reason a property-based approach works here.

**Except when they do not.** `No.` and `Date` in the Order editor, and `Salutation`, are
anonymous Edits sitting to the right of named labels. `locator.labelled()` handles those
by finding the label and taking the nearest control of the right type on the same row.

**One label can head several fields.** `ZIP - City` sits in front of a ZIP box and a City
box; `First Name Last Name` in front of two more. `locator.labelled_all()` returns them
left to right and the caller indexes in. Reading order is the rule, same as the eye uses.

**Some dropdowns have no label at all**, and sit beside a control rather than a label:
the price mode next to the Date, the Invoice's payment method next to the `paid`
checkbox. `DocumentEditor._combo_on_row_with` is `labelled()` rotated to take a control
as its anchor.

**Automation ids are numeric handles.** Nearly every control has one, which looks
promising until you notice they are values like `328444` that will not survive a restart.
Never key off them. Control type plus name is what stays put.

**Toolbar buttons are named after their tooltip**, so they read as sentences:
`'Create: New Order'`, `'Save the current contents'`.

**The left panel entries are `Text` controls**, not buttons or links, so they need a real
click. The brief's "Data > Documents" means this panel, not the menu bar.

**Alerts and selector dialogs are native `#32770` windows** hosting SWT panes, and they
are owned windows, so a plain top-level enumeration does not see them. So is the
Preferences dialog, which is why looking for it among the SWT shells finds nothing.

**The menu popups are `#32768` windows that UIA enumerates as empty.** The menu bar
itself reads fine (`MenuItem 'File'`, `'Edit'`, …) but the items inside an open menu do
not appear at all. Screenshotting the open menu and grounding the entry's text is the way
in. Worth knowing that Preferences lives under **File**, not under Extra or Window.

### The three that actually bite

**1. Tab items report logical coordinates while everything else reports physical.**

On a 200% display a tab item's rectangle is at exactly half of where the tab really is,
so a click lands somewhere else entirely. `actions.select_tab()` scales the rectangle by
the display DPI before clicking. This presents as "clicks sometimes do nothing", and only
on scaled displays.

**2. `invoke()` and `select()` succeed on tab items without switching the tab.**

No exception, no change, and the caller then looks for controls that were never realized.
`select_tab()` checks the selection state afterwards.

**3. pywinauto's `descendants()` hangs for minutes on the main window.**

Walking the identical tree with `children()` covers all 171 nodes in 0.8 seconds. The
locator does its own bounded breadth-first walk for this reason. If a lookup ever seems
to hang, this is why.

## The item grid is drawn, but its cell editor is a real widget

This is the most useful thing I learned, and it took a diagnostic rather than a theory to
find rather than the other way round.

The Items grid on a document renders as a single empty Pane: no Table, no rows, no cells.
So entering a quantity looked like the one place with no property-based route at all, and
the first implementation typed blind and read the result back from a screenshot.

It does not need to. **Double-clicking a cell adds a real `Edit` to the UIA tree**, sized
and positioned exactly over that cell, with a combo's list beside it when the column is a
dropdown. The value goes in through the same value pattern as every other field in the
project and reads back the same way. Only *aiming* the double-click is a pixel problem.

The corollary is the diagnostic lesson. The failing symptom was "double-click and F2 both
leave the value unchanged", which sounds like an activation problem and is not one. One
probe that enumerated the tree before and after the click answered it:

```
NEW controls (7):
   ('Pane',     '', '#32770',       (1164, 724, 1366, 764))
   ('List',     '', 'SysListView32',(1165, 725, 1365, 763))
   ('ListItem', 'VAT 19% (19.0%)', '', ...)
   ('Edit',     '', 'Edit',         (1164, 686, 1340, 724))
```

An editor had been opening every time. It was opening in the **VAT** column, where a
typed "2" means nothing and is discarded without complaint.

## Vision grounding fails on very wide, thin strips

Why the click was in the wrong column, and the reason it went unnoticed for three runs.

Column positions were found by asking the vision model to ground the text "Qty." on a
capture of the header. That capture is about **2300 x 60**. On an image that elongated,
the normalized boxes came back roughly **twice too far right**: the model put "Qty." at
x=204 where it is at 102, and grounding "1.00" inside a row strip of the same shape
returned 599 where the value sits at 258. Both are close to a factor of two, and both are
consistent across runs, so this is a systematic distortion rather than noise.

The same call on a normally proportioned image is reliable: it located "Preferences" in
an open menu the first time, and `read_table` reads these grids correctly all day.

So the rule is about shape, not about the model: **ground text on images with a sane
aspect ratio, and use pixels for geometry on long thin ones.** `vision.column_edges`
replaces the grounding with plain pixel work. SWT paints the column headers in one flat
colour and leaves the dividers unpainted, so a divider is a narrow gap in that colour,
and the row-header corner above `Pos.` is painted a lighter shade, which marks where the
first real column starts. No model, no API call, same answer every time.

Two independent sources still have to agree before a cell is written to. Position comes
from those pixels; column *names* come from the table read-back, which the model does
well because it is reading text rather than measuring. `order_items.py` only writes when
the editor that opened holds the value the read-back attributes to that column.

## This build's item grid has no Discount column, and the brief's does

The brief's figures 8 and 9 show an item table with about eleven columns, including
`Discount` carrying `-10.00 %`. A default Fakturama 2.2.0 shows six:

```
Pos. | Qty. | Name | VAT | U.Price | Price
```

So the brief's step 3.15, "set the line Discount to the extracted item discount", has
nowhere to write. What I checked, in order, before accepting that:

- **Preferences.** `Documents > Use discount for each item` is ticked, as is `Display a
  preview picture`. Neither column appears. Confirmed by screenshot, not only by
  `get_toggle_state`, because five checkboxes reading `True` at once looked like a UIA
  fault and turned out to be accurate.
- **Applying the preference.** Untick, retick, `Apply and Close`, then a brand new Order:
  still six columns. So it is not a value that was displayed as a default and never
  stored.
- **A column chooser.** NatTable usually offers one on a right-click. Fakturama's row
  menu offers only `move up`, `move down`, `delete`, and the header offers nothing.
- **NatTable's persisted state.** `C:\FakturamaData\fakturamaviews.properties` has
  entries for `productTable` and `debitorTreeTable` only. Nothing for a document's item
  table, so nothing to reset.
- **Width.** The editor is maximized and the table occupies about 1080px of a 2300px
  viewport. There is no shortage of room and no horizontal scrollbar.

The order-level `Discount` field at the bottom right is a different thing and is not a
substitute: it applies to the whole document. On this order it would give
`(500 + 120) x 0.9 = 558.00` against the document's `570.00`, because only line 1 is
discounted. Reverse-engineering a rate that happens to produce 570 would also break the
brief's step 3.16, which checks each line's own Price.

So the flow stops for manual review, naming the column and the line. That is the right
outcome rather than a workaround, but it does mean the sample document cannot reach
stages 4 and 5, which is why `tests/fixtures/order_without_line_discount.json` exists.

## Where UIA runs out entirely

**The selector grids are invisible.** "Select the address" and "Select a product" show
their results in a grid the tree renders as a single empty Pane. So `src/vision.py`
screenshots the grid and reads it with a vision model into dicts keyed by column name,
which is the shape `matching.py` already consumes. The grid rectangle is computed from
live control positions, never written down.

**Those dialogs also wedge the UI thread if traversed through UIA while modal.** Win32
sees the window, every UIA query times out, and input queued during the wedge replays
when the automation process dies, so selections appear to happen on their own. Three
sessions died to three symptoms of that one cause. `selector_dialog.py` speaks only
win32, screenshots and the raw keyboard.

**Screenshots must grab the framebuffer.** `capture_as_image()` goes through PrintWindow,
and SWT draws through Java, so it comes back as a black rectangle. And
`SetProcessDPIAware()` has to run before anything measures the screen.

## Four more that only show up once a document is saved

These all sit in the last two stages, and none of them is visible until an Order has
actually been saved, which is why they were the last to surface.

**Saving renames an editor tab.** "New Order" becomes "PO000005" the moment it is saved,
and "New Invoice" becomes "INV000001". Stage 5 has to come back to the Order it just
saved, and looking for "New Order" times out on an editor that is plainly on screen. The
number is read off the editor before the save and used afterwards.

**A document has to be identified by its number, not by its Cust.Ref.** Run the same
document twice and Data > Documents holds two Orders carrying the same reference. Taking
the first match silently works on the previous run's document, which presented as stage 5
being unable to find a tab: it had been told the Order was PO000001 while the tab in
front of it said PO000005. `DocumentsView.find_document` exists for this.

**A selected row in a selector dialog is a pale wash, not the saturated blue the Items
grid uses.** A colour test finds nothing on a row that is plainly selected. What tells a
selection apart from a click on the column header, which re-sorts and repaints
everything, is the *height* of what changed: one row against all of them. That is
`vision.changed_row_band`, and it is what finally fixed a failure that took two runs in
three.

**A document's address block never renders the address's `additional name`.** The sample
ships to "Northstar Office Warehouse", which is stored on the debtor's second address and
verified there when it is written. The Invoice's Delivery address tab shows the debtor,
then the street, postcode, city and country, and no warehouse name. Checking for it on
the document is checking for something Fakturama does not display; what distinguishes the
two addresses there is Beusselstrasse 44 and 10553 against Friedrichstrasse 88 and 10117.

**And an unselected tab's page does not exist.** `Tab 'Delivery address'` is absent from
the tree until its `TabItem` is selected, so asking whether a document has a delivery
address has to ask about the tab, not about its page.

## The currency locale is not cosmetic

Fakturama formats money using **Preferences > General > Currency locale**, and that
setting reaches further into the flow than it looks.

It moved to Afghanistan under me while I was opening that dialog to investigate the item
columns, and every total comparison started failing at once: amounts came back as
`۲۵۰٫۰۰ ؋`, Extended Arabic-Indic digits with the Afghani sign, which
`_as_number` correctly refuses rather than guessing at. `_as_number` now strips currency
symbols, spaces and directional marks by Unicode category rather than by a list, so
"$620.00" and "620,00 €" read alike and there are tests for both.

That fixed the parsing but not the reliability, because the euro sign does not survive
the *vision* read of the item grid: one run came back with line 1's total as "500,00
€" and line 2's as "120,00 †". A total that cannot be parsed stops the run. The locale is
set to United States for that reason, which is a deliberate choice rather than the
default it looks like.

## The one thing to understand about automating this application

**A write reports success without the application having accepted it.** Seven instances,
all found the hard way:

- `select()` on a tab returned success and did not change the page
- typing into a combo prefix-matched per keystroke and settled on a different entry
- the address type field accepted any text and rejected it on focus loss
- the date field is a segmented spinner, so "Jul 14, 2026" scattered into "Aug 20, 0026"
- the Debtor's Company was written, read back correctly, and saved empty
- clicking OK in the selector reported success while committing nothing, because OK is
  enabled whether or not a row is selected
- a quantity typed into the wrong grid column was swallowed by a VAT dropdown

The rule that falls out: **verify after the widget commits, not after the write.** An
immediate read-back only proves the characters arrived. `actions.set_text` presses Tab
first for exactly this reason.

Two riders, both learned by breaking something:

- The filter-as-you-type search box is the one field where moving focus destroys the
  value, so it passes `commit=False`.
- Fakturama reformats as it commits, turning "0" into "0%" and "0.00" into "$0.00". That
  is acceptance, not rejection, so numeric values are compared by meaning while text is
  still compared exactly.

And one worth as much as the rest: checking each field as it is written is not enough,
because a later step can undo an earlier one. Re-read the whole thing at the end of a
stage. `flow/order.py::confirm_header` exists because switching the price mode to Net
makes Fakturama recalculate the document, and the recalculation silently reset the Date.

## Things the brief words in a way that misleads

**"Open Payment and select the exact Payment Method"** (2.10) reads like a tab. It is a
`ComboBox 'Payment'` on the Miscellaneous tab, beside Discount.

**"address type"** is an `Edit`, but writing to it always fails. The real control is the
unnamed button beside it, which opens a titleless `#32770` popup holding two checkboxes,
"Invoice address" and "Delivery address".

**Switching the price mode to Net relabels the totals field** from "Total Gross" to
"Total Net". Look it up by either name.

**Billing and delivery differ on the sample document.** It ships to "Northstar Office
Warehouse" on a different street with a different postcode. The brief only walks through
the case where they match and the Main address carries both roles, so this Debtor needs a
second address via the `+` beside the address tabs.

**The brief's ordering does not work for the payment method.** Steps 2.10 to 2.10.6 say
to keep the Debtor editor open, create the payment method, then come back and select it.
The Debtor's Payment dropdown is populated when the editor opens and never refreshes:
after creating `Bank Transfer` it still offers exactly `['Pay Cash']`. So the flow
resolves the payment method *before* opening the Debtor editor. Same end state, and it
avoids either losing the entered data to a reopen or saving the wrong method.

Worth knowing alongside it: **the dropdown lists Descriptions, not Names.** It shows "Pay
Cash", the description of the method named "Cash".

## The address selector lists addresses, not debtors

The most consequential finding, because its failure mode is creating duplicates.

After saving a Debtor with two addresses, searching for it returns a row built from the
**delivery** address: postcode 10553 rather than the billing 10117, and Company blank.
The brief's exact-match rule needs Company, First Name, Name, ZIP and City to agree with
ZIP and City taken from billing, and it cannot match that row. Failing to match means
creating a second customer, and Fakturama only catches it on save with "There is already
a contact with the same name and street".

So candidates are narrowed on first and last name, which stay constant across a debtor's
addresses, and the strict check moves to *after* selection: the Order populates the
chosen debtor's invoice address, and every detail from the source document has to appear
in it. Strictness is not lost, it is applied to data that is actually reliable.

## Things that are correct behaviour, not bugs

**Stage 3 cannot be probed standalone through the whole flow.** It needs the Order that
stage 1 opens, and killing Fakturama to clear bad state discards that unsaved Order. A
*single line* can be probed cheaply though, by opening an Order and selecting one product
without involving the Debtor at all, which is how the cell-editor finding above was made.

**Kill Fakturama between runs.** An interrupted run leaves an unsaved `*New Order` open,
and a second one makes every `has_tab` lookup ambiguous. Two probes died to this before I
put a `taskkill` at the top of each run script. The symptom is a 90-second timeout
waiting for an editor that is plainly on screen.

**Fakturama degrades after repeated interrupted runs.** Its Error view starts logging
`Internal Error in: com.sebulli.fakturama.dialogs.Sele...` and `callEditor` commands stop
opening editors. That is accumulated damage from forced kills and stray modals, not a
locator problem.

**Open log files with `encoding="utf-8"`.** The vision reader returns whatever is in the
cell, including the checkmark in a Standard column, and Windows defaults to cp1252, which
cannot encode it. The run crashes at the logging line, well away from the cause.

**Views in the bottom panel are slower to open than they look.** Wait on a control
appearing, never on a sleep.

**Do not `Add-Type` in the PowerShell prelude.** Compiling C# on the fly hung
indefinitely under x64 emulation and took the whole pipeline down before Python started,
with an empty output file as the only symptom. Console minimization lives in Python
(`win32gui`) inside `session.minimize_consoles()`.

**The vision calls need patient retries, for two different reasons.** A 503 from the free
tier when the model is busy, and a raw `httpx.ConnectError` that slipped past the retry
entirely because it is a transport error rather than an `APIError` with a status code.
Retry on the transport layer as well as on status codes, and be more patient than a web
client would be: the cost of giving up is not one failed request but a half-finished flow
that has already created master data.
