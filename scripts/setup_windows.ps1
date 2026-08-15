<#
    Sets up everything the automation needs on a Windows machine.

    Run it from the repo root in PowerShell:

        powershell -ExecutionPolicy Bypass -File scripts\setup_windows.ps1

    Safe to re-run: every step checks whether it has already been done.

    Two of the steps need administrator rights and will raise a UAC prompt.
#>

[CmdletBinding()]
param(
    [string]$VenvPath = 'C:\dev\venv',
    [string]$DownloadDir = "$env:USERPROFILE\Downloads"
)

$ErrorActionPreference = 'Stop'
$curl = "$env:SystemRoot\System32\curl.exe"

function Step($message) { Write-Host "`n==> $message" -ForegroundColor Cyan }
function Note($message) { Write-Host "    $message" -ForegroundColor DarkGray }

# curl.exe rather than Invoke-WebRequest: Windows PowerShell 5.1 negotiates an old TLS
# version by default and both download hosts refuse it.
function Get-Verified($Url, $Path) {
    $expected = [int64](& $curl -sIL $Url |
        Select-String -Pattern '^content-length:\s*(\d+)' |
        ForEach-Object { $_.Matches[0].Groups[1].Value } |
        Select-Object -Last 1)

    if ((Test-Path $Path) -and (Get-Item $Path).Length -eq $expected) {
        Note "already downloaded: $(Split-Path $Path -Leaf)"
        return
    }

    Note "downloading $(Split-Path $Path -Leaf) ($([math]::Round($expected / 1MB, 1)) MB)"
    & $curl -L --silent --show-error --fail -o $Path $Url
    if ($LASTEXITCODE -ne 0) { throw "download failed: $Url" }

    # Compare against the server's length rather than just checking the file is big.
    # A transfer that dies partway leaves a plausible-looking file, and a truncated MSI
    # fails installation with a misleading "package could not be opened".
    $actual = (Get-Item $Path).Length
    if ($actual -ne $expected) { throw "truncated: got $actual bytes, expected $expected" }
}

if ($env:PROCESSOR_ARCHITECTURE -eq 'ARM64') {
    Note 'ARM64 Windows detected. Installing the x64 builds on purpose so they match'
    Note 'Fakturama, which ships x64 only. They run under emulation, which is fine here.'
}

# --- Python ------------------------------------------------------------------
Step 'Python 3.12 (x64)'
$python = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
if (Test-Path $python) {
    Note 'already installed'
} else {
    $installer = Join-Path $DownloadDir 'python-3.12.10-amd64.exe'
    Get-Verified 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe' $installer
    # Per-user, so this step needs no UAC prompt.
    Start-Process $installer -Wait -ArgumentList @(
        '/quiet', 'InstallAllUsers=0', 'PrependPath=1', 'Include_test=0'
    )
    if (-not (Test-Path $python)) { throw 'python did not install to the expected path' }
}
Note (& $python -c "import sysconfig; print('platform:', sysconfig.get_platform())")

# --- Visual C++ runtime ------------------------------------------------------
Step 'Visual C++ redistributable (x64)'
# pywinauto imports win32ui, which needs mfc140u.dll. This pywin32 build does not
# bundle MFC, so without this the uia backend fails to import at all.
if (Test-Path "$env:SystemRoot\System32\mfc140u.dll") {
    Note 'mfc140u.dll already present'
} else {
    $installer = Join-Path $DownloadDir 'vc_redist.x64.exe'
    Get-Verified 'https://aka.ms/vs/17/release/vc_redist.x64.exe' $installer
    Note 'approve the UAC prompt'
    Start-Process $installer -Verb RunAs -Wait -ArgumentList @('/install', '/quiet', '/norestart')
}

# --- Fakturama ---------------------------------------------------------------
Step 'Fakturama 2.2.0 (x64, bundled Java)'
if (Test-Path 'C:\Program Files\Fakturama2\Fakturama.exe') {
    Note 'already installed'
} else {
    $msi = Join-Path $DownloadDir 'Fakturama_2.2.0_with_jre.msi'
    Get-Verified 'https://files.fakturama.info/release/v2.2.0/Installer_Fakturama_windows-x64_2.2.0_with_jre.msi' $msi
    Note 'approve the UAC prompt'
    $p = Start-Process msiexec.exe -Verb RunAs -Wait -PassThru -ArgumentList @(
        '/i', "`"$msi`"", '/quiet', '/norestart'
    )
    if ($p.ExitCode -ne 0) { throw "msiexec failed with $($p.ExitCode)" }
}

# --- virtualenv --------------------------------------------------------------
Step "virtualenv at $VenvPath"
if (-not (Test-Path $VenvPath)) {
    New-Item -ItemType Directory -Path (Split-Path $VenvPath) -Force | Out-Null
    & $python -m venv $VenvPath
}
$venvPython = Join-Path $VenvPath 'Scripts\python.exe'
& $venvPython -m pip install --quiet --upgrade pip
& $venvPython -m pip install --quiet -r (Join-Path $PSScriptRoot '..\requirements.txt')

& $venvPython -c "import pywinauto; from pywinauto import Desktop; Desktop(backend='uia').windows(); print('pywinauto', pywinauto.__version__, 'working')"

Step 'Done'
Write-Host @"

Next:
  1. Put your Gemini API key in a .env file at the repo root:
         GEMINI_API_KEY=...
  2. Get Fakturama past its first-run dialog:
         $venvPython tools\first_run.py
  3. Run the flow:
         $venvPython run.py data\order.png
"@ -ForegroundColor Green
