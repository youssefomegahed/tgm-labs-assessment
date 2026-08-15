# Prepended to every script run through parallels_exec.sh.
#
# Parallels shares the Mac home directory at \\Mac\Home. Mapping it to a drive letter
# matters: Windows processes cope badly with a UNC current directory, and Python needs a
# normal cwd to put the repo root on sys.path.

# Minimize this console before doing anything else. The window prlctl opens lands on
# top of Fakturama, where it blocks clicks on whatever it covers and, worse, ends up
# inside the screenshots the vision layer reads tables from. A grid captured as console
# pixels reads as empty, and an empty read makes the flow create a duplicate record.
$native = Add-Type -PassThru -Name Win -Namespace Prelude -MemberDefinition @'
[DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
[DllImport("kernel32.dll")] public static extern IntPtr GetConsoleWindow();
'@
[Prelude.Win]::ShowWindow([Prelude.Win]::GetConsoleWindow(), 6) | Out-Null  # 6 = minimize

$share = $env:REPO_SHARE
if (-not $share) { $share = '\\Mac\Home\Desktop\Personal\tgm-labs\tgm-labs-assessment' }

if (-not (Test-Path 'Z:\')) {
    net use Z: \\Mac\Home /persistent:yes | Out-Null
}

$global:Repo = $share -replace '^\\\\Mac\\Home', 'Z:'
$global:VPy = if ($env:VENV_PYTHON) { $env:VENV_PYTHON } else { 'C:\dev\venv\Scripts\python.exe' }

$env:PYTHONPATH = $global:Repo
Set-Location $global:Repo
