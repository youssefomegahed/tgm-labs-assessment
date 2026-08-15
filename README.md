# Fakturama image-to-cash automation

Takes one order image, reads it, and drives Fakturama's UI until a saved Order and a
linked Invoice exist, creating the Debtor, Payment Method, VAT rates and Products along
the way if they are missing.

[DESIGN.md](DESIGN.md) is the Part 1 design document and explains the approach. This
file is how to run it.

## Where it currently stands

Honest status, because the brief says the scope is bigger than the timebox.

**Working and verified against the real application:**

- Reading the order image. All 44 fields come back matching a hand-read ground truth
  exactly, and the five arithmetic checks pass.
- Stage 1 of the brief: open a New Order, leave the proposed number alone, set the Date
  and Cust.Ref., switch the price mode to Net, confirm VAT is With VAT.
- Opening the Debtor selector from the Order using the correct upper icon rather than
  the green plus below it.
- Getting Fakturama through its first-run dialog.

**Not built yet:** the rest of stage 2 onwards. Debtor and Payment Method creation,
Product and VAT resolution, item lines, saving the Order, and the linked Invoice. The
matching rules those stages need are written and unit tested, but they are not yet
wired to the UI.

The largest open risk is the Items grid. It exposes no UIA table, so entering line
items will probably need keyboard navigation rather than addressing cells directly.

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

47 tests covering number and date parsing, the exact-match rules, and the arithmetic
validation. None of them need Windows or an API key, so they also run on a Mac.

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

## Layout

```
src/models.py        the shape of one order
src/matching.py      what counts as an exact match, and what counts as ambiguous
src/money.py         rounding, in one place
src/errors.py        including ManualReviewRequired, the deliberate stop
src/extract/         image to typed data, and the arithmetic checks on it
src/uia/             generic Windows plumbing, knows nothing about Fakturama
src/fakturama/       one class per editor or dialog, hides every locator
src/flow/            the brief's five stages (in progress)
tools/               first-run setup, and a UIA tree inspector
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
