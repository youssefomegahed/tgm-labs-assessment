#!/bin/bash
# Run a PowerShell script inside a Parallels Windows VM from the Mac host.
#
# Only needed if you are developing on a Mac like I was. On a Windows machine, ignore
# this and run the commands directly.
#
#   scripts/parallels_exec.sh some-script.ps1
#
# The script is passed as base64 of UTF-16LE via -EncodedCommand, because quoting
# survives prlctl badly otherwise. parallels_prelude.ps1 is prepended so every script
# starts with the repo share mapped and $Repo and $VPy set.
set -euo pipefail

VM="${VM_NAME:-Windows 11}"
PRLCTL="${PRLCTL:-/usr/local/bin/prlctl}"
HERE="$(cd "$(dirname "$0")" && pwd)"

if [[ $# -lt 1 ]]; then
    echo "usage: $(basename "$0") <script.ps1>" >&2
    exit 64
fi

body=$(cat "$HERE/parallels_prelude.ps1"; echo; cat "$1")
encoded=$(printf '%s' "$body" | iconv -f UTF-8 -t UTF-16LE | base64 | tr -d '\n')

"$PRLCTL" exec "$VM" --current-user powershell.exe -NoProfile -EncodedCommand "$encoded"
