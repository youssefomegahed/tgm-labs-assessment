# Fakturama image-to-cash automation

Takes one order image, reads it, and drives Fakturama's UI until a saved Order and a
linked Invoice exist, creating the Debtor, Payment Method, VAT rates and Products along
the way if they are missing.

[DESIGN.md](DESIGN.md) is the Part 1 design document and explains the approach. This
file is how to run it.

## Where it currently stands

**Working and verified against the real application, from an empty database:**

- Reading the order image. All 44 fields match a hand-read ground truth exactly, and the
five arithmetic checks pass.
- Stage 1 in full: open a New Order, leave the proposed number alone, set the price mode
to Net, confirm VAT is With VAT, set the Date and Cust.Ref., and re-read the whole
header afterwards.
- Stage 2 in full: search the address selector, take the creation branch when nothing
matches, create the missing Payment Method with its Credit transfer code, create the
Debtor with its billing address and a separate warehouse delivery address and the
right role on each, select the payment method, save once, then return to the still-open
Order, find the Debtor, select it, and confirm the populated invoice address matches
the source document field by field.
- Stage 3, product resolution: search the product selector by SKU, take the creation
branch when nothing matches, resolve the line's VAT rate first so the product form can
offer it, create the Product with the gross price calculated from the net price and the
rate, save, then re-select it onto the Order. Both branches are exercised by the sample,
which needs one product created and one selected.
- Getting Fakturama through its first-run dialog, and seeding the default Shipping
record it needs before any Order will open.

After a full run the Order holds both lines with the right unit prices and VAT rates:

```
1  1.00  Ergonomic Des...   VAT 19%  $250.00  $250.00
2  1.00  Anti-Fatigue D...  VAT 19%   $40.00   $40.00
                            Total Net $290.00  VAT $55.10  Total $345.10
```

**Written but not verified:** `src/fakturama/order_items.py`, which sets the quantity and
discount on each line. Quantities above still read 1.00 and line 1's 10% discount is not
applied, so the totals are not yet the document's 570.00 net. This is the only module in
`src/fakturama/` that has not been run against Fakturama, and its docstring lists the
assumptions a probe should check first.

**Not built:** stage 4, saving and verifying the Order, and stage 5, the linked Invoice
with its payment status.

The reason line entry is last and hardest: the Items grid has no UIA representation at
all. A tree dump of the Order editor returns zero Tables, zero DataItems and zero Lists.
Products reach it by being selected in a dialog, which works, but editing the values it
then shows has no property-based route and needs click-plus-keyboard navigation with the
result read back visually.

## What you need

- **Windows.** Microsoft UIA is Windows only. If you are on a Mac, see the last section.
- **A Gemini API key**, free tier is enough. From [Google AI Studio](https://aistudio.google.com/apikey).
Note that a project with billing switched on leaves the free tier, so a key from a
project with no billing is the simplest thing.

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

## Running it

Read and check the image without touching Fakturama:

```
C:\dev\venv\Scripts\python.exe run.py data\order.png --dry-run
```

That prints the extracted order and the arithmetic checks. Useful as a first test that
your API key works.

The full flow, with Fakturama running:

```
C:\dev\venv\Scripts\python.exe run.py data\order.png
```

To work on the UI side without spending API calls, replay a previous extraction:

```
C:\dev\venv\Scripts\python.exe run.py data\order.png --extraction tests\fixtures\expected_order.json
```

## Tests

```
C:\dev\venv\Scripts\python.exe -m pytest
```

68 tests covering number and date parsing, the exact-match and candidate rules, the
arithmetic validation, the blank-capture guard, and how a committed value is compared
against what was written. None of them need Windows or an API key, so they also run on
a Mac.

Three further tests call the model and compare its reading of `data/order.png` against
the ground truth field by field. They are opt-in because they cost API calls:

```
set RUN_LIVE_TESTS=1
C:\dev\venv\Scripts\python.exe -m pytest tests\test_extraction_live.py
```

## Resetting between runs

The flow creates master data, so a second run against the same database takes the
"already exists" branch rather than the creation branch. To exercise creation again,
close Fakturama, restore a clean copy of the data directory, and reopen:

```
Copy-Item C:\FakturamaData-clean C:\FakturamaData -Recurse -Force
```

Take that clean copy right after `tools\first_run.py` finishes, before the first run.

Do not reset by deleting the data directory. Fakturama remembers the workspace path
elsewhere, so it silently rebuilds an empty database without re-running the wizard that
seeds it, and a New Order then refuses to open with "No default value found for
Shippings". If that happens:

```
C:\dev\venv\Scripts\python.exe tools\seed_shipping.py
```

which recreates the "Free of shipping costs" default the brief expects anyway.

## Layout

```
src/models.py        the shape of one order
src/matching.py      what counts as an exact match, and what counts as ambiguous
src/money.py         rounding, in one place
src/errors.py        including ManualReviewRequired, the deliberate stop
src/extract/         image to typed data, and the arithmetic checks on it
src/gemini.py        the only file that knows which model provider is used
src/vision.py        reading grids that Fakturama draws and UIA cannot see
src/uia/             generic Windows plumbing, knows nothing about Fakturama
src/fakturama/       one class per editor or dialog, hides every locator
                     selector_dialog.py is shared by the address and product pickers
                     order_items.py is written but not yet verified
src/flow/            the brief's stages: order, debtor, products (4 and 5 to come)
tools/               first-run setup, shipping seeder, and a UIA tree inspector
scripts/             environment setup
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

Two things worth knowing if you go this route. PowerShell buffers a guest process's
output until it exits, so long-running scripts should log to a file under `runs/` on the
share and you tail that from the Mac instead. And `tools/spike_uia.py` is how I looked at
Fakturama's control tree:

```
C:\dev\venv\Scripts\python.exe tools\spike_uia.py tree --depth 6
C:\dev\venv\Scripts\python.exe tools\spike_uia.py shot runs\screen.png
```

## Notes

Fakturama shows amounts with a `$` because the guest locale is US English, while the
source document is in EUR. The brief does not ask for the currency to be changed and
nothing in the flow depends on the symbol, so I left it rather than changing a global
setting to make a screenshot look tidier.

Fakturama triggers a Windows firewall prompt on first launch. I declined it. The flow
uses the local embedded database and needs no network access.