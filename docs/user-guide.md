# Roost user guide

More detail on what bots do and what always asks. The overview is in the [README](../README.md).

## What bots can do

- **Quick, honest replies.** Every reply opens with a short "On it" line in
  words, the chat never blocks (a message to a busy bot says "Queued, I'll
  pick it up next"), and a Stuck bot says why and what to do ("Take control to
  clear it"). Hover a message to add a tapback; times are labelled Madrid.
- **Options cards and Decisions.** When a bot needs a choice it shows two to
  four options with the safe one marked, or you type your own; Dismiss counts
  as No. What you picked is listed under Decisions on its Info tab, with
  Forget so it may ask again.
- **Routines and Reports.** A routine is a name, instructions and Madrid times
  on a bot's Info tab. It runs while you are away, in its own run log, and its
  result arrives in the chat as a Report. A bot may propose a routine, but it
  starts only when you press Approve. Reminders, an end-of-day summary and
  budget alerts arrive as Reports too.
- **The question book.** A bot unsure about something that is not urgent picks
  a safe default, notes the question under Questions on Info, and carries on.
  Your answer comes back as your own message.
- **The Plan.** Each bot keeps a Plan (Calendar, Kanban or plain text) of what
  it means to do, and you can edit it. "Use the full limit until it resets"
  stays off until Roost can read your usage limit.
- **Approval modes.** Each bot is in one mode: *Ask every time*, *Auto-edit*
  or *Review first*. A hard floor (secrets, mass edits) asks in every mode.
- **Ask and Proposal cards.** A bot that needs your OK stops on an Ask card
  (Yes or No). In *Review first* it collects its changes into one Proposal
  card (Accept, Edit or Decline). Yes or Accept runs exactly what the card
  showed.
- **Mac folders.** You grant a folder on a bot's Info tab. The bot can find,
  read, create, edit, rename and trash files there; every change shows a
  diff and has Undo.
- **Your bots' computers.** Each bot can work on its own Linux computer
  (a sealed container on this Mac with a browser). Switch a bot between
  "Linux computer" and "Mac Brave" on its Info tab; a bot starts on its Linux computer.
  Open its Computer tab to watch the live screen, or "Computer is asleep"
  when it is resting. **Take control** fills the window with the bot's screen:
  your clicks, keys, scrolling and paste go to it while you hold control,
  and the bar reads "You're in control · I'm done". **I'm done** asks "Which account did you
  use?" (optional); your answer is saved as a label next to the site under
  "Vault: site logins" on the Computer tab, with Forget on each, and the bot
  is told. Roost never stores the password you type. Bot computers are not
  encrypted beyond your Mac's disk yet.

## Your bot uses its computer

A bot on its own Linux computer can use the browser there like you would:
it looks at the page, then clicks, types, presses a key or scrolls, one
step at a time, and looks again to check what happened. Its chat shows each
step ("Clicked 'Search'", "Typed into 'Search' (8 characters)", "Pressed
Enter"), and the live screen on its Computer tab shows a ring where it
clicks.

- **What just happens.** Ordinary browsing (opening menus and tabs,
  following links on the sites you named, typing your own words into a
  search box) is a *Browsing action*. Browsing actions are set to
  **Just do it** by default. Pick **Ask first** under "Browsing actions" on
  the bot's Info tab to have every click wait for your OK.
- **What always asks.** A click that would buy, send, submit, accept, delete
  or change your account always stops on an Ask card, in every approval mode,
  even Auto-edit, and even when the page tells the bot to press it. So does
  any click the bot can't classify. The card shows a picture of the button,
  its words, the site and what the bot expected. Yes checks the page again and
  clicks only that same button. Typing words you didn't write, or an email
  address, phone number or anything that looks like a password, also asks,
  and the card shows the whole text.
- **New sites ask.** The bot stays on the sites you named in the chat. A link
  to any other site asks first; Yes adds that site for this chat.
- **What it never does.** It never types into a password box, never uploads
  a file, never acts outside its browser's page, and never clicks while you
  hold its computer. What it typed is never logged or kept, and its
  screenshots are never stored.
- **When it can't.** If it misses the same button twice, or runs out of
  steps, it goes Stuck with the reason and what to do next, and a hand shows
  in its eye. **Take control**, do the step yourself, then **I'm done**: the
  bot looks at the screen again before it touches anything.

## Notes and documents

Your notes and documents (docs, sheets and PDFs) belong to you, like your tasks and money, and every bot works on the
same ones: ask a bot to "save all my tasks in a document" or "make a sheet of my October expenses".

- **Notes** are markdown with tags (`#tag` or a `tags:` front matter) and `[[links]]` to other notes. Search
  ignores case and accents. On the Board's Notes tab you search, edit with a preview and follow links.
- **Documents**: docs and sheets open in the built-in editor (Univer, only its open-source parts); PDFs open in a
  viewer. A PDF you upload counts as outside content until you press **Keep**.
- Two places editing the same note or document never overwrite each other silently: the later save is told it
  changed, and you pick **Load the latest** or **Keep mine**.
- Everything is encrypted at rest with your key: one encrypted blob per document.

## Safety notes

- **Localhost only.** Every listener (gateway, keeper, egress proxy)
  binds `127.0.0.1` and refuses to start on anything else
  (`roost/config.py::load_config`). The one exception is the gateway
  inside its Docker container, which must bind `0.0.0.0` there — allowed
  only with `ROOST_IN_CONTAINER=1`, and compose publishes it on the
  Mac's `127.0.0.1:18800` alone (pinned by `tests/test_compose.py`). Nothing here is reachable from
  another machine, except your phone over your own Tailscale network
  (`tailscale serve`, tailnet only).
- **Bots act only through gated tools.** A bot's model gets web tools
  (`open_page`, `read_page`), your records, and Mac folder tools you
  grant. On its own Linux computer it can also click and type (see "Your
  bot uses its computer"); buying, sending and submitting there always ask.
  Programs it writes run only in its own sealed workspace (below). Every tool
  call is gated and audited (`roost/talk/gate.py`), and a page's text
  always reaches the model wrapped as untrusted data, never as
  instructions.
- **Workspace containers are sealed.** A bot's programs (`run_program`) run in
  its own Docker container with no network by default (a per-bot "Internet in
  the workspace" switch turns it on; `roost/keeper/workspaces.py`), a read-only
  root filesystem, dropped capabilities, and resource limits. Your keys never
  enter it.
- **A bot's browser is egress-filtered.** Each bot's browser routes every
  request through a proxy that blocks loopback, private, link-local and
  carrier-NAT addresses and every port Roost or its predecessor binds
  (`roost/keeper/proxy.py`, `roost/desk/url_policy.py`) — a hostile page
  can't pivot a bot's browser into your home network.

