# Prepended to every script run through parallels_exec.sh.
#
# Parallels shares the Mac home directory at \\Mac\Home. Mapping it to a drive letter
# matters: Windows processes cope badly with a UNC current directory, and Python needs a
# normal cwd to put the repo root on sys.path.

# Console minimization happens in Python (src/uia/session.py) rather than here. An
# Add-Type in this prelude compiles C# on the fly, and that compile hung indefinitely
# under x64 emulation, taking the whole pipeline down with it.

# Where the repo lives on the share. Supplied by parallels_exec.sh, which derives it
# from its own location, so there is no path here to go stale when the checkout moves.
$share = $env:REPO_SHARE
if (-not $share) {
    throw "REPO_SHARE is not set. Run this through scripts/parallels_exec.sh, or set it to the repo's \\Mac\Home path yourself."
}

if (-not (Test-Path 'Z:\')) {
    net use Z: \\Mac\Home /persistent:yes | Out-Null
}

$global:Repo = $share -replace '^\\\\Mac\\Home', 'Z:'
$global:VPy = if ($env:VENV_PYTHON) { $env:VENV_PYTHON } else { 'C:\dev\venv\Scripts\python.exe' }

$env:PYTHONPATH = $global:Repo
Set-Location $global:Repo
