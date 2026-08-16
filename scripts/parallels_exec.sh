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
REPO="$(dirname "$HERE")"

if [[ $# -lt 1 ]]; then
    echo "usage: $(basename "$0") <script.ps1>" >&2
    exit 64
fi

# Where this checkout appears from inside the guest. Parallels shares the Mac home
# directory at \\Mac\Home, so the guest path is that prefix plus wherever the repo sits
# under $HOME. Worked out from this script's own location rather than written down, so a
# checkout anywhere under the home directory works with no configuration.
share="${REPO_SHARE:-}"
if [[ -z "$share" ]]; then
    case "$REPO" in
        "$HOME"/*)
            share="\\\\Mac\\Home\\$(printf '%s' "${REPO#"$HOME"/}" | tr '/' '\\')"
            ;;
        *)
            echo "the repo is outside \$HOME, so Parallels does not share it at" \
                 "\\\\Mac\\Home. Set REPO_SHARE to its guest path." >&2
            exit 78
            ;;
    esac
fi

body=$(printf "\$env:REPO_SHARE = '%s'\n" "$share"
       cat "$HERE/parallels_prelude.ps1"; echo; cat "$1")
encoded=$(printf '%s' "$body" | iconv -f UTF-8 -t UTF-16LE | base64 | tr -d '\n')

"$PRLCTL" exec "$VM" --current-user powershell.exe -NoProfile -EncodedCommand "$encoded"
