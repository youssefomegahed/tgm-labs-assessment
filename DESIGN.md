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

This is the part with no clean answer, so I use three strategies and fall through them
in order of how much I trust them.

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

I had planned a vision fallback for these, screenshotting the group and asking a model
which icon is which. It turned out not to be needed. Those two icons are unnamed
`Image` controls, but they are a tidy vertical stack in one column, 56 pixels apart, so
sorting the unnamed images below the `Addresses` label by their top edge orders them
unambiguously. Taking the first is the existing-contact selector. That is cheaper,
deterministic, and has no API dependency.

Sorting by position is not the same as hardcoding a position. The rectangles are read
off the live window on every run, so moving or resizing the form changes the answer
rather than breaking it. Only the ordering is assumed, and the ordering is what the
brief itself describes when it says "upper" and "lower".

I have kept the vision fallback in the design as the answer for any control that is
neither named nor positionally ordered, but so far nothing in the flow has needed it.

### What the spike actually found

I inspected the real tree before committing to any of this, and it changed three things.

SWT copies a field's label into the field's accessible name, so `Edit 'Cust.Ref.'` is
directly addressable and the second strategy is needed far less than I expected. It is
still needed: `No.` and `Date` are anonymous Edits sitting to the right of named labels.

Automation ids exist on almost every control, which looked promising until I noticed
they are numeric handles like `328444`. They will not survive a restart, so they are
deliberately never used as a key. Control type plus name is what stays put.

And pywinauto's own `descendants()` hangs for minutes on Fakturama's main window, while
walking the identical tree with `children()` covers all 171 nodes in 0.8 seconds. So
the locator does its own bounded breadth-first walk. That one is a library problem
rather than an application problem, but it would have sunk the whole approach if I had
taken the slow path as evidence that UIA was unworkable here.

## Knowing each step worked

Two levels of checking, because they catch different failures.

Every write reads itself back. Setting a field and moving on assumes the click landed,
the field had focus, and the widget accepted the value. Reading it back costs one
property access and turns a silent wrong value into an immediate, located failure.

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

## What the sample taught me

The delivery address on the sample document is not the billing address. It ships to
"Northstar Office Warehouse" on a different street with a different postcode. The brief
only spells out the case where the two match, where the Main address carries both
roles. So the Debtor here needs a second address with the Delivery role, which is a
branch the instructions do not walk through. Reading the data before writing the code
was worth it.

## Tradeoffs, and what I would change

**Vision model over local OCR.** Faster to a correct result and much better on the
table. The cost is an API dependency and a per-run charge. The arithmetic validation is
what makes me comfortable with a non-deterministic component in the pipeline, and
`--extraction` lets a saved reading be replayed so the UI work does not spend calls.

**Property-based grounding over image matching.** More robust, but it lives or dies on
what SWT exposes, which I cannot fully know in advance. The vision fallback is the
hedge.

**Read-back verification on every write.** Slower, and worth it. Most of the failures I
expect are silent ones.

**Scope I have not covered.** Order-level discount and shipping are held at zero, which
the sample supports and the brief allows. Single currency, single page, one document per
run. Fakturama's first-run database wizard is done by hand once rather than automated.
No Delivery, Correction or Dunning documents, as instructed.

With more time the first thing I would add is a proper reset between runs, restoring a
clean copy of the Fakturama workspace so the creation branches can be exercised
repeatedly without hand-deleting records. The second would be widening the extraction
beyond one document shape, which mostly means finding more documents to test against.
