# Fakturama Image-to-Cash: design

One order image goes in. A saved Order and a linked Invoice come out of Fakturama, with
the Debtor, the Payment Method, the VAT rates and the Products created along the way if
they were not there already.

This document covers how I read the image, how I find and drive Fakturama's controls,
how I know each step actually worked, and what I traded away.

## Where the work runs

Microsoft UIA is Windows only. I develop on an Apple Silicon Mac, so Fakturama runs in
a Windows 11 ARM VM under Parallels and the automation runs beside it in the guest.

Fakturama is an Eclipse RCP application built on SWT. That matters more than it sounds.
On Windows, SWT widgets are backed by real Win32 controls, so the UIA tree has genuine
control types and, in many places, usable names. On macOS the same widgets map to Cocoa
through a much thinner accessibility layer. Running on Windows is what makes a
property-based grounding strategy viable at all, rather than falling back to reading
pixels.

Two smaller choices follow from that. I install the x64 build of Fakturama and x64
Python rather than ARM64 ones, so the automation and the app live in the same
architecture and I never have to reason about cross-architecture UIA. Windows on ARM
emulates x64 fine, and a UI automation workload spends nearly all its time waiting on
the UI anyway. And I drive the guest with `prlctl exec` from the Mac instead of
standing up an SSH server, which is one less moving part.

## Reading the image

I send the image to a vision model with a JSON schema attached, and the API enforces
the schema. No prose to parse, no regex over OCR output, and a field that goes missing
is a schema violation rather than a silent empty string.

I went with a vision model over Tesseract because this is a layout problem more than a
character recognition problem. The item table carries meaning in its columns: a number
is a unit price or a discount or a line total depending on where it sits. Tesseract
gives me text and bounding boxes and leaves me to rebuild that structure myself, which
is work I would rather not hand-roll and then debug.

One rule in the prompt does most of the heavy lifting: **transcribe, never calculate**.
The model reports the printed line total even if it looks wrong. If I let it compute
the totals instead, then checking its arithmetic afterwards would only prove it can
multiply. Keeping it honest gives me two independent readings to compare, which is the
whole basis of the next section.

Everything comes back as strings, including the numbers. JSON numbers would arrive as
floats and floats lose cents. The strings get parsed into `Decimal` at the boundary, so
nothing downstream ever touches binary floating point.

## Trusting what came back

The extraction is checked against itself before anything reaches Fakturama:

- every line: quantity x unit net x (1 - discount) against the printed line total
- the lines sum to the printed net total
- VAT recomputed from the nets against the printed VAT total
- net plus VAT against the printed gross

On the sample all five agree. A misread digit almost always breaks at least one, and it
breaks loudly, in a way that names the field. This is cheaper and more discriminating
than running a second OCR pass and diffing text, and it needs no second model.

VAT is rounded once per rate rather than once per line. It makes no difference on a
single-rate order, but summing per-line rounded VAT drifts by a cent or two on a
mixed-rate order, and that drift would read as a genuine mismatch. There is a test that
pins this: three lines at 10.50 round to 6.00 per line and 5.99 per rate, and 5.99 is
what a document prints.

If any check fails, the run stops. A document whose own totals do not add up is exactly
what the brief means by stop for manual review, and pushing it into Fakturama would
save wrong numbers.

## Finding the controls

There is no single reliable handle for every control here, so the locator uses four
strategies and falls through them in order of how much they can be trusted.

**First, UIA properties.** Control type plus name or automation id. This is the fastest
and the most stable across window sizes, DPI and theme. Where SWT gives a control a
usable name, nothing else is needed.

**Second, anchor-relative lookup.** SWT renders a field label as its own Static control
sitting next to the field, which means the Edit itself is frequently nameless while the
label beside it is not. So I find the label, walk to its container, and take the
adjacent Edit. `Cust.Ref.`, `Street`, `ZIP`, `Value` and most of the Debtor and Product
forms are reachable this way. It survives the form being rearranged, because it depends
on the label and the field staying together rather than on either one's position.

**Third, ordering within a container.** Some controls are icons with no text anywhere
near them. The brief flags the worst case itself: beside Addresses there is an upper
icon that opens the existing-contact selector and a lower green plus that starts a new
Debtor, and clicking the wrong one silently sends the flow down the wrong branch.

Those two are unnamed `Image` controls, but they form a tidy vertical stack in one
column, so sorting the unnamed images below the `Addresses` label by their top edge
orders them unambiguously. Taking the first gives the existing-contact selector. The
same rule, rotated, handles one label heading several fields: `ZIP - City` sits in front
of a ZIP box and a City box, and reading order settles which is which.

Sorting by position is not the same as hardcoding a position. The rectangles are read
off the live window on every run, so moving or resizing the form changes the answer
rather than breaking it. Only the ordering is assumed, and the ordering is what the
brief itself describes when it says "upper" and "lower".

**Fourth, a vision fallback**, for the one place UIA runs out entirely. That is the
subject of the next section.

### What the UIA tree is actually like

Three properties of it shape everything above.

SWT copies a field's label into the field's accessible name, so `Edit 'Cust.Ref.'` is
directly addressable. This is the single biggest reason a property-based approach works
here, and it means the second strategy is needed less often than the UI's appearance
suggests. It is still needed: `No.` and `Date` are anonymous Edits beside named labels.

Automation ids exist on almost every control, but they are numeric handles like
`328444` that do not survive a restart. They are never used as a key. Control type plus
name is what stays put.

And pywinauto's own `descendants()` hangs for minutes on the main window, while walking
the identical tree with `children()` covers all 171 nodes in under a second. The locator
therefore does its own bounded breadth-first walk. That is a library problem rather than
an application one, but taking the slow path as evidence that UIA was unworkable here
would have sunk the whole approach.

## Where UIA runs out

Fakturama draws its selector grids itself. The "Select the address" and "Select a
product" dialogs have named OK and Cancel buttons and a reachable search box, but where
the result rows should be the tree holds a single empty pane: no table, no rows, no
cells. The columns the brief says to match on are simply not available as data. The
Items grid on the Order is drawn the same way.

So those are read by capturing the grid region and passing it to a vision model with the
column names and a schema, which returns rows as dicts. `matching.py` already works on
dicts of column name to text, so nothing downstream knows where the rows came from. The
region is computed from live control positions, between the search box and the OK
button, rather than written down.

Two safeguards, because this path is the least deterministic in the system. A capture
that is a single flat colour is refused rather than read, since a covered window
otherwise reads as "no rows" and an empty result sends the flow off to create a
duplicate. And the application is pinned above other windows for the duration of a run,
because a console appears with every remote command and would otherwise land in the
captures.

### A drawn grid still has real cell editors

The grid being invisible does not make the cells unreachable. **Double-clicking a cell
puts a real `Edit` into the UIA tree**, positioned exactly over that cell, with a combo's
list beside it where the column is a dropdown. So writing a quantity is an ordinary
value-pattern write with an ordinary read-back, the same as every other field in the
system, behind a click that has to be aimed.

Aiming is the part that needs pixels, and it needs them rather than a model. Column
positions come from `vision.column_edges`, which finds the dividers by plain pixel
counting: SWT paints the column headers in one flat colour and leaves the dividers
unpainted, so a divider is a narrow gap in that colour, and the lighter row-header corner
marks where the first real column begins. No API call, and the same answer every time.

Two independent sources have to agree before anything is written. Position comes from
those pixels. Column *names* come from the table read-back, which is a model call, and
which is reliable because it is reading text rather than measuring. A cell is only
written to once the editor that opened holds the value the read-back attributes to that
column on that row, and once its rectangle sits inside the column the pixels identified.
Either check failing stops the run.

### The vision fallback splits in two, and the split is not obvious

It is tempting to treat "ask a model to look at it" as one capability. It behaves as two,
with different reliability.

**Reading text out of a capture is dependable**, including on grids the tree cannot see
at all. This is what `read_table` does for the selector rows and the item lines.

**Grounding positions is dependable only on images with a sane aspect ratio.** On a
normally proportioned screenshot it is accurate enough to click by. On a very elongated
one it is not: on an item-grid header of roughly 2300 x 60 the returned boxes come back
about twice too far right, consistently rather than randomly. Since a click aimed one
column over lands in a VAT dropdown that silently discards whatever is typed, this is a
failure that produces no error at all.

So geometry on long thin strips is done with pixels, and text reading keeps the model.
The safeguard that makes the whole vision path survivable is the same one that covers
everything else here: because a write is not believed until the application has been
asked what it now holds, a wrong column produces a caught failure rather than a wrong
invoice.

## Knowing each step worked

This is the hardest part of automating this application, and the part most of the design
exists to handle.

The defining behaviour is that **a write reports success without the application having
accepted it.** It appears in many guises. A tab whose `select()` returned
cleanly and did not change the page. A dropdown that prefix-matched per keystroke and
settled on a neighbouring entry. A field that took any text and rejected it when focus
left. A date box that is a segmented spinner, so a formatted string scattered across
month, day and year. A Company that was written, read back correctly, and saved empty.
An OK button that reports itself enabled with nothing selected, so clicking it committed
nothing while looking exactly like success.

Three rules fall out of that, and together they are the design:

**Verify after the widget commits, not after the write.** An immediate read-back only
proves the characters arrived. Writes move focus away first, then check. Two riders:
the filter-as-you-type search box is the one field where losing focus destroys the
value, so it opts out; and Fakturama reformats as it commits, turning "0" into "0%",
which is acceptance rather than rejection, so numbers are compared by meaning while
text is still compared exactly.

**Re-read the whole thing at the end of a stage.** Per-field checks cannot catch a later
step undoing an earlier one, and one did: the Order's Date reverted after being verified.

**Confirm through the application's own view of saved state.** After saving a Debtor, go
back to the Order, search the selector, select it, and check the address it populates
against the source document. The editor shows what was typed; the selector shows what
was stored. This is what caught a Debtor saved without its company name, and it is what
would have caught an Order silently attached to no customer at all.

Every stage is confirmed through the application's own view of saved state. After the
Order is saved I look for it in `Data > Documents` with the expected reference, state
and total, not at the editor I just filled in. The editor shows what I typed. The
Documents list shows what Fakturama persisted, which is the thing I actually care
about. The same trick confirms a newly created Debtor or Product: rather than trusting
the save, I go back to the Order, reopen the selector, and search for it. If it can be
selected, it was saved, and I need to select it anyway.

Waiting is always polling on a condition, never a fixed sleep. The brief says "wait for
the list to stabilize", which becomes: poll the row count until it stops changing across
several consecutive reads. SWT under x64 emulation is not fast, so timeouts get real
headroom.

## Stopping rather than guessing

The brief says stop for manual review in six different places. Rather than spread that
decision through the flow, all six raise the same exception, carrying a reason and a
screenshot, caught once at the top. Ambiguity is never resolved by picking the first
row. Creating a duplicate Debtor or attaching an order to the wrong customer is worse
than stopping, and it is the kind of wrong that surfaces weeks later in someone's
accounts.

## How the code is arranged

Three layers, and no layer knows about the one two below it.

- `uia/` is generic Windows plumbing. It has never heard of Fakturama.
- `fakturama/` is one small class per editor or dialog, exposing intent like
  `set_customer_ref` or `open_address_selector`, and hiding every locator.
- `flow/` reads like the brief's five stages and never makes a raw UIA call.

The extraction side sits apart from all of it, behind a plain data model, so it can be
built and tested without Windows in the picture. That happens to be most of the risky
logic, and it is all unit tested.

Debtor, Payment Method, VAT and Product all follow the same shape: search, judge the
match, create if missing, then come back and re-select to confirm. I kept them as four
parallel implementations rather than one generic helper. Four different dialogs with
four different column sets and four different definitions of "exact" would need so much
configuration to share one function that the shared version would be harder to read
than the copies. That is a judgement, and I would revisit it if a fifth appeared.

## Where the sample departs from the brief

The delivery address on the sample document is not the billing address. It ships to
"Northstar Office Warehouse" on a different street with a different postcode. The brief
only spells out the case where the two match and the Main address carries both roles, so
this Debtor needs a second address with the Delivery role, a branch the instructions do
not walk through.

That has a consequence for matching. Fakturama's address selector lists one row per
address rather than per debtor, and the row it surfaces for a debtor with two addresses
may be the delivery one, which carries no company and a different postcode. The brief's
exact-match rule, which requires Company and the billing ZIP and City to agree, cannot
match such a row, and failing to match means creating a duplicate customer.

So candidates are narrowed on the contact's first and last name, which are the fields
that stay constant across a debtor's addresses, and the strict check moves to after the
selection: the Order populates the chosen debtor's invoice address, and every detail
from the source document has to appear in it. Strictness is not lost, it is applied to
data that is actually reliable.

## Tradeoffs, and what I would change

**Vision model over local OCR.** Faster to a correct result and much better on the
table. The cost is an API dependency and a per-run charge. The arithmetic validation is
what makes me comfortable with a non-deterministic component in the pipeline, and
`--extraction` lets a saved reading be replayed so the UI work does not spend calls.

**Property-based grounding over image matching.** More robust, but it lives or dies on
what SWT exposes. It exposes more than the UI's appearance suggests: even the drawn item
grid puts a real editor widget in the tree once a cell is activated. Pixels are kept for
the two jobs properties cannot do, measuring a drawn grid and confirming a highlight.

**Read-back verification on every write.** Slower, and worth it. Most of the failures
here are silent ones, and every one that has occurred was caught by this rather than by
the code that caused it.

**Where the application sets the ceiling.** The per-line discount cannot be entered,
because this Fakturama's item grid has no Discount column: six columns, none of them
Discount, with the preference for it ticked, no column chooser to add it, and no
persisted column state to reset. The brief's own figures show a grid with eleven. So the
flow stops for manual review naming the column and the line, rather than approximating
with the order-level Discount field, which applies to the whole document and would give
558.00 against this document's 570.00.

**Scope I have not covered.** Order-level discount and shipping are held at zero, which
the sample supports and the brief allows. Single currency, single page, one document per
run. Fakturama's first-run database wizard is done by hand once rather than automated.
No Delivery, Correction or Dunning documents, as instructed.

Everything here has been proven against one document. The mixed-rate VAT rounding, the
branch where billing and delivery match, and the unpaid branch of stage 5 are all
implemented and unit tested where they can be, and none of them has met the application.
A second source document is what would change that, and it is the first thing I would
add.
