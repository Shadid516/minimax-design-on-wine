---
name: minimax-design-on-wine
description: Install, repair, and daily-drive MiniMax Design (MiniMax's Windows-only AI design/video desktop app, no Linux version) under WINE on Linux — silent NSIS install, KDE launcher with the real icon, browser-login deep-link bridge for minimax-hub:// callbacks, quitting past the "Project protection is incomplete. Quit was cancelled" veto, auto-updates via the official Velopack CDN feed, and healing "index-has-live-owner" asset/canvas breakage. Use whenever the user mentions MiniMax Design, MiniMax Hub, or the Hailuo/design desktop client on Linux or WINE, or reports any of those exact symptoms with it — even if they only say "MiniMax Design won't start/quit/update/log in on Linux".
---

# MiniMax Design on WINE — complete Linux setup

MiniMax Design (design.minimax.io) is a Windows/macOS Electron app with no
Linux build. It runs well under WINE once five infrastructure gaps are
bridged. Everything below was validated end-to-end on WINE 11, Debian 13,
KDE X11, Intel iGPU + NVIDIA GTX 1060. The general patterns (they apply to
other Windows Electron apps too) are in
[references/general-wine-electron-patterns.md](references/general-wine-electron-patterns.md).

The app self-reports as supported under WINE's Windows 10.19045 reporting;
keep software rendering (the app offers this itself after its GPU process
crashes — accept "Restart Now"; GPU passthrough on WINE+NVIDIA is the flaky
part and the UI is web-based, so software rendering is smooth).

## 0. Quick reference

| Thing | Value |
|---|---|
| Installer | `MiniMax Design-<ver>-x64-Setup.exe` (NSIS, silent flag `/S`) |
| Install dir | `C:\users\<user>\AppData\Local\Programs\MiniMax Design\` |
| Real binary | `current\MiniMax Design.exe` (stub `MiniMax Design.exe` + `Update.exe` beside it) |
| Installed version | `current\sq.version` (nuspec XML `<version>` element) |
| Deep-link scheme | `minimax-hub` (`HKCU\Software\Classes\minimax-hub`) |
| Uninstall key | `HKCU\...\Uninstall\com.minimax.hub.global` |
| App logs | `AppData\Roaming\@hilo\MiniMax Hub Global\logs\` |
| App data / index | `AppData\Roaming\@hilo\MiniMax Hub Global\output_files\.hilo\` |
| Project storage | `C:\users\<user>\Movies\Hub\Projects\<project>\` (real user data) |
| Release feed | `https://file.cdn.minimax.io/public/minimax-hub/release/overseas/releases.win.json` |
| Installer URL | `…/overseas/MiniMax%20Design-<ver>-x64-Setup.exe` |
| Update policy | `…/overseas/update-policy.json` (`min_supported_version`) |
| WM_CLASS | `minimax design.exe` (title `MiniMax Design`) |

Never modify files inside `current\` — the app verifies resource integrity at
startup and a modified bundle breaks it. Bridge around the app at the OS level.

## 1. Install (silent)

```sh
WINEDEBUG=-all wine "$HOME/Downloads/MiniMax Design-3.0.16-x64-Setup.exe" /S
```

`/S` (capital S) is a fully silent NSIS install — the same installer later
updates in place, which is what makes the external updater (section 5) work.

## 2. Launcher, menu entry, icon

Launcher script `~/.local/bin/minimax-design` — note the three load-bearing
details: writer-state pruning before start (section 6), **stdio redirection on
the exec line** (portals launch handlers with stdout/stderr *closed*; Electron
then dies with an EBADF "JavaScript error occurred in the main process"
dialog), and the post-quit update-check hook:

```sh
#!/bin/sh
# prune stale index-writer state from previous sessions (see section 6)
if ! pgrep -f "[M]iniMax Design.exe" >/dev/null 2>&1; then
    appdata="$HOME/.wine/drive_c/users/$USER/AppData/Roaming/@hilo/MiniMax Hub Global"
    projects="$HOME/.wine/drive_c/users/$USER/Movies/Hub/Projects"
    find "$appdata" "$projects" -type d -name writers -path "*index-recovery*" -exec rm -rf {} + 2>/dev/null
    find "$appdata" "$projects" -type d -name writer-locks -path "*index-recovery*" -exec rm -rf {} + 2>/dev/null
    find "$appdata" "$projects" -type f -name "candidate-*.json" -path "*index-recovery*" -exec rm -f {} + 2>/dev/null
fi
env WINEDEBUG=-all WINEPREFIX="$HOME/.wine" \
    wine "C:\\users\\$USER\\AppData\\Local\\Programs\\MiniMax Design\\MiniMax Design.exe" "$@" \
    </dev/null >/dev/null 2>&1
systemctl --user start minimax-design-autoupdate.service 2>/dev/null &
```

`.desktop` entry at `~/.local/share/applications/minimax-design.desktop`:
`StartupWMClass=minimax design.exe` (so windows group under the launcher),
`Icon=minimax-design`. Extract the icon from the exe — the app ships no icon
files and typical systems lack icoutils/pip:

```sh
scripts/extract-icon.py ".../MiniMax Design/current/MiniMax Design.exe" \
    ~/.local/share/icons/hicolor/256x256/apps/minimax-design
```

Then `kbuildsycoca6`.

## 3. Login: bridge `minimax-hub://` into WINE

Sign-in opens the **Linux** browser and returns to `minimax-hub://auth-callback?accessToken=<JWT>`.
That scheme exists only in the WINE registry, so the browser drops the
redirect. The registry's command line is the contract: the URL arrives as
`argv` to `current\MiniMax Design.exe`, and Electron's single-instance lock
hands it to the running instance.

```sh
scripts/register-scheme-handler.sh minimax-hub \
    'C:\users\'"$USER"'\AppData\Local\Programs\MiniMax Design\current\MiniMax Design.exe' \
    minimax-design
```

This writes `~/.local/bin/minimax-design-url-handler` (with the stdio redirect
baked in — without it the second instance crashes with EBADF *before* the
handoff and the login token is silently lost), registers it via
`xdg-mime default`, and refreshes the desktop database.

- Test before a real login: `xdg-open "minimax-hub://test"` — a second instance
  should appear briefly and hand off. Firefox may cache its handler table and
  prompt once ("open xdg-open?"); Chrome follows xdg-mime immediately.
- Never log the full callback URL — it carries a bearer token. The generated
  handler logs a 40-char prefix only; scrub any token already in a log with
  `sed -i 's/accessToken=.*/accessToken=[scrubbed]/' <logfile>`.

## 4. Quitting: the "Project protection is incomplete" veto

On exit the gateway backs up and verifies each workspace index, comparing
`dev/ino/birthtimeMs` and re-hashing the SQLite file. Under WINE those checks
misfire (its own backup changes the file's hash; birthtime semantics differ),
so **every quit is vetoed** and the same failure breaks the gateway's internal
restarts. It cannot be patched (integrity-checked resources) — so quit out of
band. Force-killing is safe: projects are plain files on disk and the index is
crash-safe SQLite whose backups are derived data only (receipts record
`canvasHash: null`).

Use the bundled helper (`scripts/wine-app-quit.sh` + `scripts/x-graceful-close.py`):
WM_DELETE to the windows → 20 s grace → `wineserver -k` → SIGKILL leftovers:

```sh
WINE_APP_PATTERN='[M]iniMax Design.exe' WINE_WINDOW_CLASS='minimax design' \
    scripts/wine-app-quit.sh
```

Install it as `~/.local/bin/minimax-design-quit` plus a "Quit MiniMax Design"
menu entry — the discoverable path when the in-app veto dialog appears.
Caveat: `wineserver -k` kills **all** WINE apps of the user. On Wayland
sessions the graceful X11 step no-ops and the helper goes straight to force.

## 5. Auto-updates (replacing the broken in-app updater)

The in-app Velopack updater fails permanently under WINE ("install location
could not be verified", `SIGNATURE_QUERY_FAILED` → "switching to manual
recovery"): its install-ownership check shells out to
`System32\WindowsPowerShell\v1.0\powershell.exe`, which doesn't exist in a
WINE prefix. The red "Update failed" panel is permanent — replace the
mechanism. `releases.win.json` on the CDN is the authoritative feed (trust it
over `latest.yml`, which can be stale).

`scripts/wine-app-autoupdate.sh` with these env values:

```sh
FEED_URL="https://file.cdn.minimax.io/public/minimax-hub/release/overseas/releases.win.json"
SETUP_URL_BASE="https://file.cdn.minimax.io/public/minimax-hub/release/overseas"
SETUP_NAME_FMT='MiniMax Design-%s-x64-Setup.exe'
INSTALL_ROOT='C:\users\<user>\AppData\Local\Programs\MiniMax Design'
VERSION_FILE="$HOME/.wine/drive_c/users/$USER/AppData/Local/Programs/MiniMax Design/current/sq.version"
```

It compares versions (integer tuples), defers while the app runs (never
install over a running instance), downloads (~400 MB), verifies the PE magic,
installs with `wine Setup.exe /S`, confirms the version file bumped, and
notifies via `notify-send`. Automate with a systemd **user** timer
(`~/.config/systemd/user/minimax-design-autoupdate.{service,timer}`:
`OnBootSec=10min`, `OnUnitActiveSec=12h`, `Persistent=true`, `Environment=DISPLAY=:1`)
— `systemctl --user enable --now minimax-design-autoupdate.timer`. The
launcher's post-quit hook (section 2) also checks right after the app closes.

## 6. Healing "index-has-live-owner" / broken assets & canvas

The app runs **one gateway per workspace** (app-level + one per project;
projects are real user data under `Movies/Hub/Projects/` — never delete
project directories). Each workspace index keeps writer-ownership records in
`<…>/.hilo/index-recovery/index.sqlite/`: `identity.json`, `latest.json`,
`write-epoch.json`, backups (keep), plus runtime artifacts — `writers/`,
`writer-locks/`, `candidate-*.json` (safe to prune, app closed).

Unclean exits leave stale records; WINE's PID recycling and stat quirks then
make the next session's gateways block each other: `index-has-live-owner`,
`index-preflight-failed ENOENT` → `/api/assets` and canvas requests fail and
quit is vetoed. The launcher's prune (section 2) makes every start
self-healing. After pruning and relaunching, expect: 0 failed
`/api/assets`, 0 canvas failures, and possibly **one benign** `boot reconcile
… index-has-live-owner` error per boot (app-level housekeeping meets the
project gateway's legitimate lock — ignore it).

Cluster the app's logs to confirm health:

```sh
grep -ihE '\[error\]|"level":"error"' "$HOME/.wine/drive_c/users/$USER/AppData/Roaming/@hilo/MiniMax Hub Global/logs/main-"*.log \
  | sed -E 's/^\[[^]]*\] //; s/[0-9a-f-]{36}/UUID/g; s/[0-9]{2,}/N/g' \
  | sort | uniq -c | sort -rn | head -15
```

The in-app diagnostics export (zip into the Documents folder) is a good
snapshot: `local_gateway`/`cloud_gateway_api`/`app_api` probes `ok`,
`windowsVersion … status: supported` mean the WINE base is sound.

## 7. Known-unfixable under WINE (accept and move on)

- In-app updater panel ("Update failed") — replaced by section 5.
- `unknown_backend dropped media_type=audio backend=minimax_music_cover` —
  server-side catalog config; no client-side fix.
- Renderer memory warnings — software-rendering overhead (correct trade-off).
- `rebuildNativeMenus: windowService not ready, dock menu skipped` — cosmetic.
- One benign boot-reconcile ownership error per launch (section 6).

## 8. Validation checklist

1. `wine Setup.exe /S` exits 0; `current\MiniMax Design.exe` exists.
2. Menu entry launches; windows group under the extracted icon.
3. `xdg-open "minimax-hub://test"` hands off with no error dialog (validates
   the stdio fix).
4. A real login completes — the browser redirect lands in the app.
5. `minimax-design-quit` leaves `pgrep -cf "[M]iniMax Design.exe"` at 0 and the
   update check fires.
6. Autoupdate run manually reports "up to date" (or installs).
7. Close→relaunch cycle shows no `index-has-live-owner` in fresh logs.
