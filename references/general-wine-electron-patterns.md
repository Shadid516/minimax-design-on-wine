# General patterns: Windows Electron apps under WINE

The MiniMax Design walkthrough in SKILL.md is one instance of five failure
classes that recur across Windows Electron apps run under WINE. This file is
the app-agnostic version — use it when adapting this skill's approach to a
different app.

| # | Symptom | Root cause | Fix |
|---|---------|-----------|-----|
| 1 | No Linux version; installer is a Windows .exe | — | Silent install: NSIS installers accept `/S` (capital S). Per-user Electron installs land in `C:\users\<user>\AppData\Local\Programs\<App>\`; Velopack layout = stub exe + `Update.exe` beside `current\`. |
| 2 | Login opens the browser, redirect never returns | Custom `scheme://` handler exists only in the WINE registry | Register the scheme on the Linux side (`xdg-mime default`) with a handler that execs the WINE exe with the URL as argv — mirror the WINE registry command verbatim. Electron's single-instance lock delivers it to the running instance. |
| 3 | "JavaScript error in the main process: EBADF / createWritableStdioStream" | Process launched with stdio fds *closed* (`.desktop`/portal launches) | Redirect on the exec line: `</dev/null >/dev/null 2>&1`. In deep-link handlers the crash otherwise happens before the single-instance handoff, silently swallowing the payload. |
| 4 | App refuses to quit ("protection"/"cleanup" dialog) | Exit guards verify file identity/hashes assuming Windows stat semantics (e.g. stable `st_birthtime`); WINE differs | Graceful-then-force quit: WM_DELETE_WINDOW to the app's windows → grace period → `wineserver -k`. Safe when user data is plain files + crash-safe SQLite and the guard protects derived indexes only — verify once in the app's logs/receipts before deciding. |
| 5 | In-app updater fails permanently | Velopack/Squirrel verify install ownership via Windows machinery (markers, registry, PowerShell) | Replace the mechanism: poll the vendor's release feed (`releases.win.json` — authoritative; `latest.yml` can be stale), compare versions, and when the app is closed, download the official Setup.exe and run it with `/S` (updates in place, keeps shortcuts). Automate with a systemd user timer. |

## Discovery commands (unknown app)

```sh
# install dir + layout
find "$WINEPREFIX/drive_c/users/$USER/AppData/Local/Programs" -maxdepth 2 -name "*.exe"
# custom URL schemes (HKCU and HKLM)
grep -hoiE '^\[Software\\\\Classes\\\\[a-z0-9.-]+\]' "$WINEPREFIX/user.reg" "$WINEPREFIX/system.reg" \
  | grep -viE 'microsoft|windows|clsid'
# fallback: scan the bundle
strings ".../current/resources/app.asar" | grep -oE '[a-z0-9-]+://'
# update feed hints
strings ".../current/resources/app.asar" | grep -E 'cdn|latest.yml|releases'
# window class for StartupWMClass / graceful close
xwininfo -root -tree
```

## Diagnosis method

Cluster before reading: normalize timestamps/UUIDs/numbers out of the app's
error logs, `sort | uniq -c | sort -rn`, and treat the dominant cluster as the
root cause — the rest is usually fallout. Correlate error timestamps with
backend/gateway start lines; first-boot failures with `errno: ENOENT` are
often the app probing for something that legitimately doesn't exist yet.

Watch for repeated `…-has-live-owner` / ownership-blocked opens: apps running
one backend process per workspace leave writer/lock records behind unclean
exits, and WINE PID recycling makes live-checks pass against the wrong
process. Prune only the runtime ownership artifacts (writers/, writer-locks/,
candidate markers) while the app is closed, and bake the prune into the
launcher so every start self-heals. Never delete project data.

## Principles

- Never patch files inside the app bundle — Electron bundles are
  integrity-checked at startup. Bridge around the app at the OS level.
- Never log full deep-link URLs; auth callbacks carry bearer tokens.
- `wineserver -k` terminates all WINE apps of the user, not just one.
- Validate the whole daily-driver loop: install → launch/menu → scheme handoff
  → real login → quit → update check → clean relaunch.
