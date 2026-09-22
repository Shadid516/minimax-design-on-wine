---
name: minimax-design-on-wine
description: Install, repair, and daily-drive MiniMax Design (MiniMax's Windows-only AI design/video desktop app, no Linux version) under WINE on Linux — silent NSIS install, KDE launcher with the real icon, browser-login deep-link bridge for minimax-hub:// callbacks, quitting past the "Project protection is incomplete. Quit was cancelled" veto, auto-updates via the official Velopack CDN feed, healing "index-has-live-owner" asset/canvas breakage ("Network Error"), and stopping the "restore projects?" dialog that reappears on every boot. Use whenever the user mentions MiniMax Design, MiniMax Hub, or the Hailuo/design desktop client on Linux or WINE, or reports any of those exact symptoms with it — even if they only say "MiniMax Design won't start/quit/update/log in on Linux".
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
| App config store | `AppData\Roaming\@hilo\MiniMax Hub Global\hub-config-global.json` (holds `workspaceRestoreHealth`, section 4b) |
| KDE autostart entry | `~/.local/share/applications/wine/Programs/MiniMax Design.desktop` (session restore) |
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
details: preflight state normalization before start (section 6), **stdio
redirection on the exec line** (portals launch handlers with stdout/stderr
*closed*; Electron then dies with an EBADF "JavaScript error occurred in the
main process" dialog), and the post-quit update-check hook:

```sh
#!/bin/sh
# normalize runtime state left by the previous (unclean) session — section 6
[ -x "$HOME/.local/bin/minimax-design-preflight" ] && "$HOME/.local/bin/minimax-design-preflight"
env WINEDEBUG=-all WINEPREFIX="$HOME/.wine" \
    wine "C:\\users\\$USER\\AppData\\Local\\Programs\\MiniMax Design\\MiniMax Design.exe" "$@" \
    </dev/null >/dev/null 2>&1
systemctl --user start minimax-design-autoupdate.service 2>/dev/null &
```

`.desktop` entry at `~/.local/share/applications/minimax-design.desktop`:
`StartupWMClass=minimax design.exe` (so windows group under the launcher),
`Icon=minimax-design`. Extract the icon from the exe — the app ships no icon
files and typical systems lack icoutils/pip. The extractor reads the exe from
stdin and writes the image to stdout, so you control all paths:

```sh
mkdir -p ~/.local/share/icons/hicolor/256x256/apps
scripts/extract-icon.py --png < ".../MiniMax Design/current/MiniMax Design.exe" \
    > ~/.local/share/icons/hicolor/256x256/apps/minimax-design.png
```

(Use `--ico` to dump every icon size as an ICO container instead.)
Then refresh the caches: `kbuildsycoca6` and
`update-desktop-database ~/.local/share/applications`.

### Critical: also patch the WINE-generated desktop entry

On KDE, the app is usually auto-relaunched at every login by **session
restore**, which launches the WINE-generated entry
`~/.local/share/applications/wine/Programs/MiniMax Design.desktop` directly —
bypassing any custom launcher. If preflight does not run on that path, stale
state builds up again within days. Point the entry's `Exec=` at a wrapper
that normalizes state first, then starts the app exactly as before:

```sh
# scripts/minimax-design-launch-lnk — preflight, then launch the .lnk
# scripts/minimax-design-integration-fix — rewrites the entry's Exec= to the
#   wrapper (backs up first, idempotent); safe to re-run any time.
```

The app's Velopack updates can rewrite that entry (winemenubuilder), so the
auto-updater re-runs `integration-fix` after each successful update — verify
`grep '^Exec=' ".../wine/Programs/MiniMax Design.desktop"` still points at the
wrapper after any update. To confirm what launches the app at boot, check
`~/.local/state/plasmasessionrestorestaterc` for
`appId=wine-Programs-MiniMax Design.desktop`, or inspect the transient unit
`systemctl --user cat 'app-wine\x2dPrograms\x2dMiniMax\x20Design@*.service'`.

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

### Close it automatically at logout/shutdown

Without this, every PC shutdown or logout kills the app uncleanly and feeds
the restore-health counters (section 6) — the dialog then returns on the next
boot. Plasma 6 **removed** the old `~/.config/plasma-workspace/shutdown/`
script directory (verified against startplasma.cpp — only `env/` scripts
remain), so use a systemd user service whose `ExecStop` runs in the session
teardown path:

```ini
# ~/.config/systemd/user/minimax-design-session-guard.service
[Unit]
Description=Close MiniMax Design orderly at session end
DefaultDependencies=no
Before=shutdown.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/bin/true
ExecStop=/home/<user>/.local/bin/minimax-design-shutdown-quit
TimeoutStopSec=20

[Install]
WantedBy=default.target
```

`systemctl --user enable --now minimax-design-session-guard.service`; the stop
script (`scripts/minimax-design-shutdown-quit`) sends WM_DELETE, waits ~4 s,
then `wineserver -k`. Test it safely while logged in:
`systemctl --user stop minimax-design-session-guard.service` must leave
`pgrep -cf "[M]iniMax Design.exe"` at 0. Allow ~15 s of `TimeoutStopSec`
headroom for the forced path.

## 4b. The "restore projects?" dialog on every boot

Symptom: a warning dialog at startup asking whether to restore workspaces,
listing recently-used projects, appearing after every reboot. Cause: the
app's **restore circuit breaker**. It keeps a per-workspace unclean-exit
counter in `hub-config-global.json` (key `workspaceRestoreHealth`); the
counter increments on each *startup workspace restore* and is cleared only by
a *clean* exit. Under WINE exits are never clean (section 4), so the counter
only grows — at `RESTORE_UNHEALTHY_THRESHOLD = 2` the dialog fires on every
boot and the store entry keeps climbing (observed streaks 5–6).

Fix: reset the counter while the app is closed, before every launch. The
preflight script does this (alongside the writer-state prune) and refuses to
touch the file while the app runs:

```sh
scripts/minimax-design-preflight   # resets workspaceRestoreHealth → {}
```

It preserves everything else in the store (login tokens, projects, layout)
and writes a `.preflight-bak` copy before its first edit. Because the
threshold is 2 and preflight resets to 0 before each launch, the counter can
never reach the dialog. If the dialog does appear (e.g. app started without
preflight), the safe answer is **Skip** — the same workspaces are reopenable
from the home screen, and preflight will have cleared the counters by the
next start.

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

The app shows this as **"Network Error"** in the UI (asset/canvas panes blank
or spinning). Cluster the app's logs to confirm health:

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
- In-app quit is always vetoed — use the quit helper / session guard (section 4).
- 2–3 `Failed to fetch` errors in the first ~2 s of each boot: a startup race
  between the renderer and the gateways becoming healthy (gateways come up
  1.5–2.5 s after the renderer starts under WINE). Requests succeed on retry;
  0 failures after the gateways are healthy. Don't chase it.
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
6. Autoupdate run manually reports "up to date" (or installs); after an
   update, the WINE desktop entry's `Exec=` still points at the wrapper
   (`minimax-design-integration-fix` re-ran).
7. Close→relaunch cycle shows no `index-has-live-owner` in fresh logs.
8. Two consecutive unclean exits (e.g. two force-quits) followed by a launch
   through the wrapper: **no restore dialog** at startup (preflight reset the
   counters) and `workspaceRestoreHealth` in `hub-config-global.json` stays
   empty while the app is closed.
9. `systemctl --user stop minimax-design-session-guard.service` closes a
   running app and leaves 0 processes.
