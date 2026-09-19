#!/bin/sh
# Check the vendor's Velopack release feed and silently install updates for a
# Windows (WINE) desktop app whose in-app updater cannot work under WINE.
#
# Environment:
#   FEED_URL       https://…/releases.win.json (Velopack; Assets[].Version/Type)
#   SETUP_URL_BASE https://…/  base dir holding "App Name-<ver>-x64-Setup.exe"
#   SETUP_NAME_FMT printf format for the installer filename, %s = version
#                  (default: 'App Name-%s-x64-Setup.exe' — override!)
#   INSTALL_ROOT   WINE-side install dir, e.g.
#                  "C:\users\<user>\AppData\Local\Programs\App Name"
#   VERSION_FILE   path (Linux-side) of a file containing the installed
#                  version; Velopack: <INSTALL_ROOT unix path>/current/sq.version
#                  (nuspec XML; version extracted from <version>…</version>)
#   WINEPREFIX     default ~/.wine
#   NOTIFY         1 to notify-send progress (default 1)
#
# Behavior: app running -> defer with a notification. App closed -> download,
# verify PE magic, run "wine Setup.exe /S", confirm the version file bumped,
# notify. Intended to run from a systemd user timer (e.g. boot+10min, 12h).
set -u
FEED_URL="${FEED_URL:?set FEED_URL}"
SETUP_URL_BASE="${SETUP_URL_BASE:?set SETUP_URL_BASE}"
SETUP_NAME_FMT="${SETUP_NAME_FMT:-App Name-%s-x64-Setup.exe}"
INSTALL_ROOT="${INSTALL_ROOT:?set INSTALL_ROOT}"
VERSION_FILE="${VERSION_FILE:?set VERSION_FILE}"
WINEPREFIX="${WINEPREFIX:-$HOME/.wine}"
NOTIFY="${NOTIFY:-1}"
LOG="${LOG:-$HOME/.local/state/$(basename "$0").log}"

log() { echo "$(date -Is) $*" >> "$LOG"; }
note() { [ "$NOTIFY" = "1" ] && command -v notify-send >/dev/null && notify-send "App update" "$1"; }

mkdir -p "$(dirname "$LOG")"
log "--- update check start ---"

[ -f "$VERSION_FILE" ] || { log "ERROR: version file missing: $VERSION_FILE"; exit 1; }
local_ver=$(sed -n 's:.*<version>\(.*\)</version>.*:\1:p' "$VERSION_FILE" | head -1)
[ -n "$local_ver" ] || { log "ERROR: cannot parse local version"; exit 1; }

feed=$(curl -sS --max-time 30 "$FEED_URL") || { log "ERROR: feed fetch failed"; exit 1; }
remote_ver=$(printf '%s' "$feed" | python3 -c \
    'import json,sys; d=json.load(sys.stdin); print(max(a["Version"] for a in d["Assets"] if a.get("Type")=="Full"))') \
    || { log "ERROR: feed parse failed"; exit 1; }

log "installed=$local_ver latest=$remote_ver"
python3 -c "import sys; ta=tuple(map(int, sys.argv[1].split('.'))); tb=tuple(map(int, sys.argv[2].split('.'))); sys.exit(0 if ta > tb else 1)" \
    "$remote_ver" "$local_ver" || { log "up to date"; exit 0; }

# Match the app by its exe path fragment so multiple WINE apps can coexist.
APP_EXE_FRAGMENT=$(printf '%s' "$INSTALL_ROOT" | sed 's/.*[\\\/]//')
if pgrep -f ".*[\\/]${APP_EXE_FRAGMENT}[\\/].*\.exe" >/dev/null 2>&1; then
    log "update available but app is running; deferring"
    note "Version $remote_ver is available. Close the app; it will install on the next check."
    exit 0
fi

setup_name=$(printf "$SETUP_NAME_FMT" "$remote_ver")
tmp_exe="${TMPDIR:-/tmp}/wine-app-update.exe"
url="$SETUP_URL_BASE/$(printf '%s' "$setup_name" | sed 's/ /%20/g')"
log "downloading $url"
curl -sS -L --max-time 3600 -o "$tmp_exe" "$url" \
    || { log "ERROR: download failed"; note "Update to $remote_ver failed to download."; exit 1; }
head -c2 "$tmp_exe" | grep -q "MZ" \
    || { log "ERROR: downloaded file is not a PE executable"; rm -f "$tmp_exe"; exit 1; }

log "installing $remote_ver silently"
if WINEDEBUG=-all WINEPREFIX="$WINEPREFIX" wine "$tmp_exe" /S >> "$LOG" 2>&1; then
    sleep 5
    new_ver=$(sed -n 's:.*<version>\(.*\)</version>.*:\1:p' "$VERSION_FILE" | head -1)
    if [ "$new_ver" = "$remote_ver" ]; then
        log "update to $remote_ver installed successfully"
        note "Updated to version $remote_ver."
    else
        log "WARNING: installer ran but version file reports ${new_ver:-unknown}"
        note "Update to $remote_ver finished (version file reports ${new_ver:-unknown})."
    fi
else
    log "ERROR: silent installer exited nonzero"
    note "Update to $remote_ver failed to install."
fi
rm -f "$tmp_exe"
log "--- update check done ---"
