# Sign-in, instructions, research and workspace internet fixes (2026-10-23)

Owner decisions of 2026-10-23, part A. Each piece is test-first, staged by name and committed on its own.

## A1. Vault: save a login only when the computer looks signed in

- I'm done on a **Sign-in card** (`POST /api/stuck/{id}/clear` with `account` and/or `keep`) saves a Vault: site
  login only when the bot's Linux computer looks signed in to the card's host:
  - the sign-in page detector (`roost/desk/stuck.py`) sees no sign-in (or code) page on the bot's **front tab**
    (the front tab becomes the bot's tab first), and
  - the browser holds at least one cookie for the host or a parent domain (`cookie_covers`, never a public
    suffix), read by fixed CDP `Storage.getCookies` (`roost/desk/site_data.py`, the host validated first).
- Otherwise nothing is saved, the card stays open, and the route answers **409** "You don't look signed in to
  <host> yet, so nothing was saved." (`roost/signin/check.py`, `not_signed_in_text`). An unreachable computer is
  503 as before; a sleeping one counts as not signed in.
- Desks gain `sign_in_signals(host)` (KeeperDesk, FakeDesk; the `Desk` protocol line is left to the merge since
  `roost/desk/__init__.py` is being edited elsewhere). The fake jar starts with `.login.example`, the default
  scripted sign-in site.
- Mac Brave bots and plain Stuck cards: unchanged.

## A2. A bot updates its own instructions in your own chat

- New tool `update_my_instructions(section, new_text, why)`: in a **clean 1:1 run started by your own message** it
  changes the named section (Who you are and context · What you do · Rules · Tone · Team,
  `roost/bots/instruction_sections.py`) directly and posts an `instruction_change` chat line
  "Updated my instructions: <section>" with **Undo**.
- Undo (`POST /api/instruction-changes/{message_id}/undo`, `roost/instruction_proposals/changes.py`) restores the previous text with a
  compare-and-swap on the bot's instructions: it applies only while the instructions are still exactly what the
  change wrote, so an Undo never overwrites a newer change (409 otherwise).
- In a tainted run, a handoff, a room or a routine it is refused, and the bot uses `propose_instructions_update`
  (the "Update my instructions?" card) as today.
- Every bot's prompt: when the owner asks you to change how you behave, update your instructions; when the owner
  asks to see your instructions, show them in full (they are the owner's).
- Web: the `instruction_change` line with Undo.

## A3. Research: `web_search`

- `web_search(query)` is a read tool. It opens one fixed search host (`WEB_SEARCH_URL`, DuckDuckGo's plain HTML
  page) in the bot's own browser (the desk's `search_page`: `open_page`, then the document's HTML by fixed CDP
  `DOM.getOuterHTML`; no new HTTP client, no page script), parses up to `WEB_SEARCH_MAX_RESULTS` (10) results
  (title, url, snippet; ads and non-http links left out, DuckDuckGo's redirect links decoded) with the standard
  library (`roost/research/`), and returns them escaped as untrusted. Helpers may use it (the locked desk).
- It taints the run like any page and adds each result's host to the run's link scope, so `open_page` may open
  them (the scope is extended where `open_page`'s scope lives today).
- Scripted and test mode: FakeDesk serves a fixture results page for the search host.

## A4. Internet in the workspace

- A per-bot switch "Internet in the workspace" (Profile → Computer tab, Workspace files area), off by default,
  owner-only route `PUT /api/bots/{id}/workspace-internet`, stored on the bot (`bots.workspace_internet`,
  **schema v34**; v33 is taken by routine permissions).
- On: the workspace container `roost-desk-<id>` is started on the bot's own `roost-net-<id>` network with
  `HTTP_PROXY` / `HTTPS_PROXY` pointing at `roost-egress` (public hosts only; private ranges and Roost ports
  refused by the existing egress rules). Off: no network, as today. Switching recreates the container; the
  workspace files (its volume) are kept.
- The keeper (`roost/keeper/workspaces.py`) remembers the switch per bot and labels the container
  `app.roost.internet=1`, so a restart reads it back; `POST /desks/{id}/workspace/internet` sets it. Retire removes
  the workspace before the computer, since the computer's removal deletes the network.
- Keys still never enter the sandbox. run_program's description and the prompt (`programs_text`) say whether the
  workspace has internet. With internet on, what the workspace gives back (a program's output, a file, a listing)
  may be web content, so it taints the run like a page.
