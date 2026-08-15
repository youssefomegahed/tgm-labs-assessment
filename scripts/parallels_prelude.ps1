# Prepended to every script run through parallels_exec.sh.
#
# Parallels shares the Mac home directory at \\Mac\Home. Mapping it to a drive letter
# matters: Windows processes cope badly with a UNC current directory, and Python needs a
# normal cwd to put the repo root on sys.path.

$share = $env:REPO_SHARE
if (-not $share) { $share = '\\Mac\Home\Desktop\Personal\tgm-labs\tgm-labs-assessment' }

if (-not (Test-Path 'Z:\')) {
    net use Z: \\Mac\Home /persistent:yes | Out-Null
}

$global:Repo = $share -replace '^\\\\Mac\\Home', 'Z:'
$global:VPy = if ($env:VENV_PYTHON) { $env:VENV_PYTHON } else { 'C:\dev\venv\Scripts\python.exe' }

$env:PYTHONPATH = $global:Repo
Set-Location $global:Repo
