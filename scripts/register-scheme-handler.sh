#!/bin/sh
# Register a Linux x-scheme-handler that forwards custom-URL redirects
# (browser login callbacks) into a WINE app as a command-line argument.
#
# Usage:
#   register-scheme-handler.sh <scheme> <wine-windows-exe-path> [app-name]
#
# Example:
#   register-scheme-handler.sh myscheme \
#     "C:\\users\\$USER\\AppData\\Local\\Programs\\App Name\\App Name.exe" app-name
#
# Why the stdio redirect matters: desktop portals launch the handler with
# stdout/stderr CLOSED. Electron's bootstrap touches process.stderr, gets
# EBADF and dies before Electron's single-instance handoff — the login token
# in the URL is silently lost and a "JavaScript error in the main process"
# dialog appears. The redirect on the exec line prevents this. Do not remove.
set -eu
SCHEME="${1:?usage: register-scheme-handler.sh <scheme> <wine-exe-path> [app-name]}"
EXE="${2:?usage: register-scheme-handler.sh <scheme> <wine-exe-path> [app-name]}"
APP="${3:-$SCHEME-app}"

BIN="$HOME/.local/bin"
DESK="$HOME/.local/share/applications"
mkdir -p "$BIN" "$DESK"

handler="$BIN/$APP-url-handler"
cat > "$handler" <<EOF
#!/bin/sh
# Forwards $SCHEME:// deep links into the WINE app. The redirect is load-bearing.
log="\$HOME/.local/state/$APP-url-handler.log"
mkdir -p "\$(dirname "\$log")"
[ \$# -gt 0 ] || exit 0
echo "\$(date -Is) \$(printf '%s' "\$1" | cut -c1-40)" >> "\$log"
exec env WINEDEBUG=-all WINEPREFIX="${WINEPREFIX:-\$HOME/.wine}" \\
    wine "$EXE" "\$1" </dev/null >/dev/null 2>&1
EOF
chmod +x "$handler"

cat > "$DESK/$APP-url-handler.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=$APP (URL handler)
Exec=$handler %u
Terminal=false
NoDisplay=true
MimeType=x-scheme-handler/$SCHEME;
EOF

xdg-mime default "$APP-url-handler.desktop" "x-scheme-handler/$SCHEME"
command -v update-desktop-database >/dev/null && update-desktop-database "$DESK"
command -v kbuildsycoca6 >/dev/null && kbuildsycoca6 >/dev/null 2>&1
echo "registered: xdg-mime reports '$(xdg-mime query default "x-scheme-handler/$SCHEME")'"
echo "test with:  xdg-open '$SCHEME://test'  (app should hand off to its running instance)"
