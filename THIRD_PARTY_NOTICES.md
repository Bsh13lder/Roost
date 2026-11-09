# Third-Party Notices

Roost is MIT-licensed and only takes on MIT / Apache-2.0 / BSD / ISC /
MPL-2.0 dependencies. Any code borrowed from another MIT/Apache project
(rather than just depended on) gets an SPDX header at the top of the file
plus an entry here.

## Fonts

The web face uses the system font stack (`web/src/styles/tokens.css`,
look & feel redesign P1) and ships no font files.

## Harvested from LazyClaw (MIT, same author)

Copied from LazyClaw @ `21e1002` and adapted; each file says so in its header.

| Roost file | LazyClaw source |
|---|---|
| `roost/tasks/nl_time.py` | `lazyclaw/tasks/nl_time.py` |
| `roost/tasks/reminders.py` | `lazyclaw/tasks/pre_reminders.py` |
| `roost/tasks/steps.py`, `roost/tasks/recurrence.py`, `roost/tasks/due.py` | `lazyclaw/tasks/store.py`, `lazyclaw/heartbeat/cron.py` |
| `roost/tasks/format.py`, `roost/tasks/tool_specs.py` | `lazyclaw/skills/builtin/task_manager.py` |
| `roost/records/resolver.py` | `lazyclaw/budgets/resolver.py` |
| `roost/money/*` (names and semantics) | `lazyclaw/budgets/store.py`, `lazyclaw/skills/builtin/budget_manager.py` |
| `web/src/components/board/taskChips.ts` | `web/src/components/tasks/taskHelpers.ts` |
| `web/src/components/board/money.ts` | `web/src/components/budgets/money.ts` |
| `roost/notes/wikilinks.py`, `roost/notes/frontmatter.py`, `roost/notes/text.py` | `lazyclaw/lazybrain/wikilinks.py`, `frontmatter.py`, `store.py` |
| `roost/documents/doc_snapshot.py`, `roost/documents/markdown_blocks.py` | `lazyclaw/docs/snapshot.py`, `lazyclaw/docs/markdown_blocks.py` |
| `roost/documents/sheet_snapshot.py`, `roost/documents/sheet_text.py` | `lazyclaw/sheets/snapshot.py`, `lazyclaw/skills/builtin/sheets.py` |
| `roost/documents/pdf_ops.py` | `lazyclaw/pdf/ops.py` |
| `roost/documents/store.py`, `roost/gateway/routes/documents.py` (semantics) | `lazyclaw/{docs,sheets,pdf}/store.py`, `lazyclaw/gateway/routes/{docs,sheets,pdf}.py` |
| `web/src/components/notes/wikilink.ts`, `web/src/components/notes/noteHelpers.ts` | `web/src/lib/wikilink.ts`, `web/src/components/notes/noteHelpers.ts` |
| `web/src/components/documents/univer/docKit.ts`, `sheetKit.ts`, `DocumentOpen.tsx`, `PdfViewer.tsx` | `web/src/pages/Docs.tsx`, `Sheets.tsx`, `Documents.tsx`, `Pdf.tsx` |

## Adapted from Univer (Apache-2.0)

`web/src/components/documents/univer/createUniver.ts` adapts `createUniver` from `@univerjs/presets` 0.24.0
(`lib/es/index.js`), Copyright 2023-present DreamNum Co., Ltd., licensed under the Apache License, Version 2.0
(https://www.apache.org/licenses/LICENSE-2.0; the text ships in `web/node_modules/@univerjs/core/LICENSE`). Roost
installs the individual open-source presets instead of that meta package, which pulls in Univer's paid
`@univerjs-pro/*` line (spec §3.1); `web/tests/licenseGate.test.ts` fails on any `@univerjs-pro` package.

Depended on, not copied: `@univerjs/core`, `@univerjs/themes`, `@univerjs/preset-docs-core`,
`@univerjs/preset-sheets-core` and their `@univerjs/*` dependencies (Apache-2.0 — `@univerjs/telemetry`'s
package.json has no license field; its LICENSE file is Apache-2.0, a reviewed entry in `web/tests/licenseGate.ts`),
`pdfjs-dist` (Apache-2.0), `react-pdf`, `react-markdown` and `remark-gfm` (MIT); server side `pypdf` (BSD-3-Clause),
`pdfplumber` (MIT) and `reportlab` (BSD).

## Adapted from OpenMausBot (Apache-2.0)

OpenMausBot — Copyright 2026 Milind Soni and OpenMausBot contributors (from its `NOTICE`).
Adapted from commit `3b1f6de`, files outside `enterprise/` only; each adapted file carries an SPDX
header and says what changed. The full license text is in `LICENSES/Apache-2.0.txt`.
The OpenMausBot and MausBot names, its mascot, `CursorAvatar` and expressions are not used.

| Roost file | OpenMausBot source |
|---|---|
| `roost/bots/limits.py` | `shared/bot-profile.ts` (`fitsOnOneLine`) |
| `roost/desk/control.py` | `server/computer-control.ts`, `server/control-client.ts` (the control rules) |
| `web/src/components/WorkingIndicator.tsx` | `src/components/WorkingIndicator.tsx`, `src/lib/working-time.ts` |
| `web/src/components/FoldCard.tsx` | `src/components/AskCard.tsx` |
| `roost/bots/redact.py` | `shared/redact.ts` (the secret patterns) |
| `web/src/lib/botProfile.ts` | `shared/bot-profile.ts` (`fitsOnOneLine`) |

Ideas only, no code copied: the shape of `create_bot` (`server/drivers/agents-catalog.ts`), the template
file's in/out rules (`docs/team-sharing.md`), and the "an over-limit draft is never sent" rule (`src/lib/soul.ts`).

## noVNC (MPL-2.0)

`@novnc/novnc` 1.7.0, installed from npm exactly as published (no patch, no fork), by the Computer tab's live
screen. It is reached only through `web/src/lib/novnc.ts` and loads as its own lazy chunk. Copyright the noVNC
authors (see `web/node_modules/@novnc/novnc/AUTHORS`); license text in `web/node_modules/@novnc/novnc/LICENSE.txt`.
Source: https://github.com/novnc/noVNC. Its bundled pako is MIT.

## Computers 2.0

- **noVNC** (MPL-2.0): npm `@novnc/novnc@1.7.0`, unmodified, source at https://github.com/novnc/noVNC. It loads
  only as the Computer tab's own lazy chunk. Its bundled **pako** (MIT) comes with it.
- **The seccomp profile** (Apache-2.0): `roost/keeper/seccomp/chromium.json`, adapted from moby/profiles
  `seccomp/default.json` (Copyright Docker, Inc. / the Moby authors) at the commit the C0 spike used, with five
  syscalls allowed (`clone`, `clone3`, `unshare`, `setns`, `chroot`) so Chromium's own sandbox can start.

Programs in the `roost-computer` image (`docker/computer/Dockerfile`), each a separate, unmodified Debian package
that Roost starts as its own process and never links:

- TigerVNC `Xvnc` (GPL-2.0+): Roost speaks RFB to its Unix socket, nothing more.
- JWM (MIT), xterm (X11), tini (MIT).
- The desktop: PCManFM (GPL-2.0+), LXTerminal (GPL-2.0+), GPicView
  (GPL-2.0+), the Papirus icon theme (GPL-3.0), DejaVu fonts (Bitstream Vera licence) and tzdata (public domain).
  The wallpaper is drawn at build time by Roost's own `make_wallpaper.py`.
- Brave Browser (MPL-2.0, with Chromium's BSD-3-Clause and its bundled licences), the `brave-browser` package
  from Brave's official apt repo (release channel), unmodified; its licence texts ship in the package
  (`brave://credits`). Source: https://github.com/brave/brave-browser. Roost starts it as its own process and
  sets only command-line flags and a managed policy file (`docker/computer/brave-policies.json`).
- The GNU userland and the shared libraries listed by `docker/computer/licences.sh` at build time.
- `python3` (PSF), for `roost-computerd`, `roost-pipe` and `roost-input`.
- xdotool and its library libxdo3 (BSD-3-Clause), a separate, unmodified Debian package: `roost-input` runs the
  `xdotool` program for the computer-use loop's clicks, keys and typing (C3), and never links it.

`roost-egress` (`docker/egress/Dockerfile`) is `python:3.12-slim-bookworm` (PSF and Debian packages) plus Roost's own
proxy code.
