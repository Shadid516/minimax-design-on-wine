#!/bin/sh
# Graceful-then-force quit for a Windows (WINE) desktop app whose exit guard
# vetoes normal quitting under WINE.
#
# Sequence: WM_DELETE to the app's windows (same as clicking X) -> wait
# GRACE_SECONDS -> wineserver -k -> SIGKILL leftovers. Then run
# WINE_POST_QUIT_HOOK if set (e.g. trigger an update check).
#
# Environment:
#   WINE_APP_PATTERN   pgrep -f pattern matching the app's exe   (required)
#   WINE_WINDOW_CLASS  WM_CLASS substring for graceful close     (default: derived)
#   WINEPREFIX         WINE prefix                               (default ~/.wine)
#   GRACE_SECONDS      how long to wait for a graceful exit      (default 20)
#   WINE_POST_QUIT_HOOK command run after the app is gone        (optional)
#
# Safety: force-kill is acceptable when the app stores user data as plain
# files + crash-safe SQLite and its exit guard protects derived indexes only
# (verify once in the app's logs/receipts). wineserver -k terminates ALL WINE
# apps of this user.
set -u
PATTERN="${WINE_APP_PATTERN:?set WINE_APP_PATTERN, e.g. '[A]pp Name.exe'}"
WINEPREFIX="${WINEPREFIX:-$HOME/.wine}"
GRACE="${GRACE_SECONDS:-20}"
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)

if [ -z "${WINE_WINDOW_CLASS:-}" ]; then
    WINE_WINDOW_CLASS=$(printf '%s' "$PATTERN" | tr -d '[]' | sed 's/\.exe$//;s/.*[\\\/]//')
fi

# 1) ask nicely
for win in $(DISPLAY="${DISPLAY:-:1}" xwininfo -root -tree 2>/dev/null \
             | grep -iE "0x[0-9a-f]+ \"[^\"]*${WINE_WINDOW_CLASS}[^\"]*\"" \
             | grep -oE '0x[0-9a-f]+' | sort -u); do
    python3 "$SCRIPT_DIR/x-graceful-close.py" --display "${DISPLAY:-:1}" "$win" 2>/dev/null
done

# 2) wait for a graceful exit
i=0
while [ "$i" -lt "$GRACE" ]; do
    pgrep -f "$PATTERN" >/dev/null 2>&1 || { echo "graceful exit"; HOOK=done; break; }
    sleep 1; i=$((i + 1))
done

# 3) force-terminate if still alive
if pgrep -f "$PATTERN" >/dev/null 2>&1; then
    WINEPREFIX="$WINEPREFIX" wineserver -k 2>/dev/null
    sleep 4
    pgrep -f "$PATTERN" >/dev/null 2>&1 && pkill -9 -f "$PATTERN" 2>/dev/null
    sleep 2
    echo "force-closed (exit guard vetoed graceful quit; safe for file+sqlite-backed apps)"
fi

if [ "${HOOK:-}" = "done" ] || [ "${1:-}" = "--hook-anyway" ] || [ -n "${WINE_POST_QUIT_HOOK:-}" ]; then
    [ -n "${WINE_POST_QUIT_HOOK:-}" ] && sh -c "$WINE_POST_QUIT_HOOK" &
fi
