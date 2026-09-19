# MiniMax Design on WINE — the complete Linux setup

[MiniMax Design](https://design.minimax.io) (MiniMax's AI design/video agent
desktop app) ships only Windows and macOS builds. This is an
[agent skill](https://github.com/anthropics/skills) — a `SKILL.md` plus
battle-tested helper scripts — that documents a **fully working daily-driver
setup under WINE on Linux**, including fixes for the parts that normally
break:

- **Install** — silent NSIS install (`wine Setup.exe /S`), launcher + KDE menu
  entry, and extracting the real app icon from the `.exe` (pure-stdlib PE
  parser, no icoutils/pip needed).
- **Login** — MiniMax authenticates in your Linux browser and redirects to a
  custom `minimax-hub://` URL that only exists inside the WINE registry, so
  the redirect silently dies. This skill registers a Linux-side scheme
  handler that forwards the callback into the app (and fixes the EBADF
  "JavaScript error in the main process" crash that otherwise eats the login
  token).
- **Quitting** — the app's quit-time "project protection" veto under WINE
  ("Project protection is incomplete. Quit was cancelled.") is unfixable by
  design (Windows stat/hash assumptions + integrity-checked resources), so
  the skill ships a graceful-then-force quit helper and explains why
  force-killing is safe (projects are plain files; the protected index is
  rebuildable crash-safe SQLite).
- **Updates** — the in-app Velopack updater can never verify its install
  under WINE (it shells out to Windows PowerShell). The skill replaces it
  with an external auto-updater: polls the official `releases.win.json` CDN
  feed, downloads the official installer, and silently updates in place —
  on a systemd user timer and right after you close the app.
- **Runtime health** — MiniMax runs one backend gateway per workspace;
  unclean exits leave stale writer-ownership records that make the next
  session fail with `index-has-live-owner` (broken assets/canvas) and quit
  vetoes. The launcher prunes that state on every start (self-healing),
  without ever touching project files.

Also documented: what is genuinely **not fixable** under WINE (in-app updater
panel, some server-side catalog warnings) and the one benign error per boot
you can safely ignore.

Validated end-to-end on WINE 11 / Debian 13 / KDE X11 / NVIDIA (software
rendering), MiniMax Design 3.0.16.

## Installing the skill

Copy or clone into your agent's skill directory:

```sh
git clone https://github.com/Shadid516/minimax-design-on-wine.git \
    ~/.agents/skills/minimax-design-on-wine
```

ZCode, Claude Code, and similar agent tools discover `SKILL.md` there
automatically. Humans can simply read `SKILL.md` top to bottom — it's a
complete, ordered walkthrough.

## Layout

```
SKILL.md                                    the full walkthrough (8 sections)
references/general-wine-electron-patterns.md  app-agnostic patterns (other Windows apps)
scripts/extract-icon.py                     PE icon extractor (pure stdlib)
scripts/register-scheme-handler.sh          minimax-hub:// → WINE bridge installer
scripts/wine-app-quit.sh                    graceful-then-force quit helper
scripts/x-graceful-close.py                 X11 WM_DELETE_WINDOW sender
scripts/wine-app-autoupdate.sh              Velopack feed watcher / silent updater
```

## Scope & safety notes

- Everything bridges around the app at the OS level — no file inside the app
  bundle is ever modified (they are integrity-checked at startup).
- `wineserver -k` terminates all WINE apps of your user, not just one.
- Deep-link callback URLs carry bearer tokens: the handler logs only a
  40-character prefix; never paste full callback URLs anywhere.
