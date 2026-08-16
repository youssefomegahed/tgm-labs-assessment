# Fakturama image-to-cash automation

Takes one order image, reads it, and drives Fakturama's UI until a saved Order and a
linked Invoice exist, creating the Debtor, Payment Method, VAT rates and Products along
the way if they are missing.

- [DESIGN.md](DESIGN.md) is the Part 1 design document and explains the approach.
- [NOTES.md](NOTES.md) is what driving the real application taught me: the behaviours
  that cost real time to find and are in no documentation.
- This file is how to run it, and where it stands.

## Where it currently stands

All five stages are implemented and have run end to end against the live application in
one continuous session, ending with Invoice INV000001 saved as paid beside its still-open
Order PO000005. [docs/screenshots](docs/screenshots) holds the annotated evidence, and
says under each image which run it came from: three are from that continuous run, and one
is the Debtor existence check captured separately against the live application.

**Verified end to end, from the extraction through to a saved, paid Invoice:**

- Reading the order image. All 44 fields match a hand-read ground truth exactly, and the
  five arithmetic checks pass.
- **Stage 1**: open a New Order, leave the proposed number alone, set the price mode to
  Net, confirm VAT is With VAT, set the Date and Cust.Ref., and re-read the whole header
  afterwards.
- **Stage 2**: search the address selector, take the creation branch when nothing
  matches, create the missing Payment Method with its Credit transfer code, create the
  Debtor with its billing address and a separate warehouse delivery address and the right
  role on each, select the payment method, save once, then return to the still-open
  Order, find the Debtor, select it, and confirm the populated invoice address matches
  the source document field by field.
- **Stage 3**: resolve each Product by SKU, take the creation branch when nothing
  matches, resolve the line's VAT rate first so the product form can offer it, create the
  Product with the gross price calculated from the net price and the rate, save,
  re-select it onto the Order, then set the line's quantity and confirm the line total.
- **Stage 4**: confirm the Order's totals against the document, save once, and find the
  saved row in Data > Documents by the document number Fakturama allocated.
- **Stage 5**: create the Invoice from the Order's own follow-up action rather than the
  toolbar, confirm everything Fakturama copied across, set the payment method, apply the
  paid status with its date and value, save once, and verify in Data > Documents that the
  Invoice is listed as paid for the right total while its source Order is still there,
  still open, and unchanged.

**One thing does not work, and it is not the code: this Fakturama's item grid has no
Discount column.** The brief's own figures show one, carrying `-10.00 %`. A
default Fakturama 2.2.0 shows six columns and none of them is Discount:

```
Pos. | Qty. | Name | VAT | U.Price | Price
```

So the brief's step 3.15 has nowhere to write, and the sample document's 10% discount on
line 1 cannot be entered. The flow stops for manual review naming the column and the
line, which is the correct outcome, but it does mean the sample document stops in stage 3
and never reaches stages 4 and 5.

I checked five things before accepting that: the preference (`Documents > Use discount
for each item` is ticked), applying it explicitly, a NatTable column chooser on
right-click, NatTable's persisted column state on disk, and whether the table was simply
short of room. [NOTES.md](NOTES.md) has the detail. The order-level Discount field at the
bottom right is a different quantity and is not a substitute: applied to this order it
gives 558.00 against the document's 570.00, because only line 1 is discounted.

To exercise stages 4 and 5 despite that, there is a second fixture,
[`tests/fixtures/order_without_line_discount.json`](tests/fixtures/order_without_line_discount.json),
which is the same document with the line discount removed and every total recomputed. It
is clearly labelled as not being a reading of the image. See
[Running it](#running-it) below.

## What you need

- **Windows.** Microsoft UIA is Windows only. If you are on a Mac, see the last section.
- **A Gemini API key**, free tier is enough, from [Google AI Studio](https://aistudio.google.com/apikey).
  A project with billing switched on leaves the free tier, so a key from a project with
  no billing is the simplest thing.

Everything else the setup script installs.

## Setup

From the repo root, in PowerShell:

```
powershell -ExecutionPolicy Bypass -File scripts\setup_windows.ps1
```

It is safe to re-run, and it will raise two UAC prompts. It installs:

- Python 3.12 **x64**, deliberately not ARM64 even on an ARM machine, so it matches
  Fakturama, which ships x64 only
- the Visual C++ redistributable, which `pywinauto` needs indirectly: it imports
  `win32ui`, which needs `mfc140u.dll`, which this `pywin32` build does not bundle
- Fakturama 2.2.0 with bundled Java
- a virtualenv at `C:\dev\venv` with the Python dependencies

Then put your key in a `.env` file at the repo root:

```
GEMINI_API_KEY=your-key-here
```

And get Fakturama past its first-run dialog, which asks for a working directory:

```
C:\dev\venv\Scripts\python.exe tools\first_run.py
```

That puts the database in `C:\FakturamaData` (override with `FAKTURAMA_DATA`). Fakturama
restarts itself once during this step, which the script waits for.

**Take a clean copy of the data directory now**, before the first run, so the creation
branches can be exercised again later:

```
Copy-Item C:\FakturamaData C:\FakturamaData-clean -Recurse
```

## Running it

Read and check the image without touching Fakturama:

```
C:\dev\venv\Scripts\python.exe run.py data\order.png --dry-run
```

That prints the extracted order and the arithmetic checks, and is the quickest test that
your API key works.

The full flow, against the real document:

```
C:\dev\venv\Scripts\python.exe run.py data\order.png
```

This runs stages 1 to 3 and then stops for manual review at line 1's discount, for the
reason above. To see stages 4 and 5, run the same flow against the derived fixture:

```
C:\dev\venv\Scripts\python.exe run.py data\order.png --extraction tests\fixtures\order_without_line_discount.json
```

To work on the UI side without spending API calls, replay the real extraction:

```
C:\dev\venv\Scripts\python.exe run.py data\order.png --extraction tests\fixtures\expected_order.json
```

**Close Fakturama before each run.** An interrupted run leaves an unsaved `*New Order`
open, and a second one makes every editor lookup ambiguous, which presents as a
90-second timeout waiting for an editor that is plainly on screen. The run scripts under
`runs/` all start with a `taskkill` for this reason.

## Resetting between runs

The flow creates master data, so a second run against the same database takes the
"already exists" branch rather than the creation branch. To exercise creation again,
close Fakturama and restore the clean copy:

```
Copy-Item C:\FakturamaData-clean C:\FakturamaData -Recurse -Force
```

Do not reset by deleting the data directory. Fakturama remembers the workspace path
elsewhere, so it silently rebuilds an empty database without re-running the wizard that
seeds it, and a New Order then refuses to open with "No default value found for
Shippings". If that happens:

```
C:\dev\venv\Scripts\python.exe tools\seed_shipping.py
```

which recreates the "Free of shipping costs" default the brief expects anyway.

## Tests

```
C:\dev\venv\Scripts\python.exe -m pytest
```

101 tests covering number and date parsing, the exact-match and candidate rules, the
arithmetic validation, the blank-capture guard, how a committed value is compared against
what was written, reading amounts back across currency locales, and the two pixel reads
of the drawn grids, each against a real capture: the Items grid's column detection, and
the rule under a selector's column header that a row click has to be aimed below. None of
them need Windows or an API key, so they also run on a Mac.

Three further tests call the model and compare its reading of `data/order.png` against
the ground truth field by field. They are opt-in because they cost API calls:

```
set RUN_LIVE_TESTS=1
C:\dev\venv\Scripts\python.exe -m pytest tests\test_extraction_live.py
```

## Layout

```
src/models.py           the shape of one order
src/matching.py         what counts as an exact match, and what counts as ambiguous
src/money.py            rounding, in one place
src/errors.py           including ManualReviewRequired, the deliberate stop
src/extract/            image to typed data, and the arithmetic checks on it
src/gemini.py           the only file that knows which model provider is used
src/vision.py           reading and measuring surfaces that Fakturama draws itself
src/uia/                generic Windows plumbing, knows nothing about Fakturama
src/fakturama/          one class per editor or dialog, hides every locator
                        document_editor.py is what the Order and Invoice editors share
                        selector_dialog.py is shared by the address and product pickers
src/flow/               the brief's five stages
tools/                  first-run setup, shipping seeder, and a UIA tree inspector
scripts/                environment setup
docs/screenshots/       annotated evidence, with each image's provenance
```

The layering rule is that no layer knows about the one two below it. `flow/` never makes
a raw UIA call, and `uia/` has never heard of Fakturama.

## Developing from a Mac

This was built on an Apple Silicon Mac with Windows 11 ARM in Parallels. The repo lives
on the Mac and is shared into the guest, so there is one copy of the code.

`scripts/parallels_exec.sh` runs a PowerShell script inside the VM from the Mac, which
avoids setting up SSH:

```
scripts/parallels_exec.sh some-script.ps1
```

It maps the Mac home directory to `Z:` in the guest and sets `$Repo` and `$VPy`.
Override `VM_NAME`, `REPO_SHARE` or `VENV_PYTHON` if your paths differ.

Two things worth knowing if you go this route. **PowerShell buffers a guest process's
output until it exits**, so a long run gives no sign of life until it finishes or hangs;
anything slow should write to a log under `runs/` on the share, which you then read from
the Mac. Those logs come back as UTF-16, so `iconv -f UTF-16LE -t UTF-8` before reading
them. And `tools/spike_uia.py` is how I looked at Fakturama's control tree:

```
C:\dev\venv\Scripts\python.exe tools\spike_uia.py tree --depth 6
C:\dev\venv\Scripts\python.exe tools\spike_uia.py shot runs\screen.png
```

## Notes

Fakturama shows amounts with a `$`, while the source document is in EUR. Its currency
formatting comes from **Preferences > General > Currency locale**, which is set to United
States here. The brief does not ask for the currency to be changed, and nothing in the
flow depends on the symbol: `_as_number` strips currency symbols by Unicode category, so
it reads "$620.00" and "620,00 €" alike, and there are tests for both.

United States is nonetheless a deliberate choice rather than an accident. With the locale
on Germany the flow works but is measurably less reliable, because the euro sign does not
survive the vision read of the item grid: one run came back with line 1's total as
"500,00 €" and line 2's as "120,00 †". A total that cannot be parsed stops the run. `$`
has read correctly every time.

Fakturama triggers a Windows firewall prompt on first launch. I declined it. The flow
uses the local embedded database and needs no network access.

## Written question: what would I do with three more hours?

**First, the two things that are wrong rather than missing.**

The line discount. I would stop treating the missing column as final and go one level
deeper than the UI: Fakturama's item rows are JPA entities in an embedded HSQLDB, and the
question I have not answered is whether this build simply never renders that column or
whether the underlying field is there and reachable. If it is a rendering decision, the
next thing to try is a different Fakturama version, since the brief's own figures show a
grid this one does not have. Half an hour of that would either produce the column or turn
"we cannot enter a discount" into a precise, citable statement about the build, and both
are better than where it stands.

The selector dialog's `choose`. It walks candidate row heights until a click changes some
pixels, then commits with Enter. It works most of the time and failed once in the runs
behind this README, on a row it had already found. It is the least principled code in the
project and the only place still guessing at geometry. Now that I know cell editors are
real widgets, I would check whether these grids expose anything similar on double-click,
which would replace the guessing entirely.

**Then, the thing that would most change my confidence.** Everything here has been proven
against exactly one document. I would write a second one by hand with a deliberately
awkward shape, two VAT rates, a debtor whose billing and delivery match, an unpaid status,
and run the whole flow against it. Single-rate rounding, the `delivery_is_billing` branch
and the unpaid branch of stage 5 are all implemented and none has ever executed. The
mixed-rate rounding in particular is unit tested and has never met the application.

**And the cheap ones I would take if the above went well.** A `--from-stage` flag, because
a failure in stage 5 currently costs a full ten-minute rerun of stages 1 to 4. Saving a
screenshot automatically at every `ManualReviewRequired` rather than at some of them,
since NOTES.md records three separate occasions where a screenshot answered in one look
what three theories had not. And a real reset command, since restoring the workspace by
hand is the step most likely to be got wrong by someone running this for the first time.
