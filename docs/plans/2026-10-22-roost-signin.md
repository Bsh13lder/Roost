# Roost: the Sign-in card (design note, 2026-10-22)

**What.** A bot on its **Linux computer** that meets a sign-in page stops on a **Sign-in card** instead of a
plain Stuck card. Owner decisions: you decide whether each login is kept; a kept login lives only in the bot's
Chromium profile, and the AI never sees the password. Roost never sees your password, and the card says so.

- **Opened by** the stuck detector (reason `login`), `ask_for_help` whose reason names a sign-in (sign in, log
  in, login…), or the new tool `request_sign_in(site, why)` (your own chat only, like `ask_for_help`). It is a
  Stuck card (`stuck_cards`, the same store, state machine, status line and My turn) with `sign_in = 1`, set
  only when the bot's computer is Linux. **Mac Brave bots keep today's Stuck card.**
- **Buttons: Open sign-in · Check again · Later.** Open sign-in = `POST /api/stuck/{id}/open-sign-in`: you take
  control, and the bot's own Chromium goes to the card's page if it is elsewhere; the web opens the full-screen
  Take control. You type the password yourself on the live screen. Check again = `/clear` with
  `how: "try_again"`. Later = `POST /api/stuck/{id}/later`: the card closes (`given_up`) and the bot says it
  left that site for later.
- **I'm done** asks "Which account did you use?" (optional) and **"Keep me signed in on this computer?"**
  Yes / No, this time. `/clear` takes `keep: true | false`.
  - Yes: Vault: site logins gets (or keeps) the row with `kept = 1`. The session stays in the profile volume.
  - No: the row is `kept = 0` with `clear_after_item_id` = the continue item. When that item is no longer
    queued or running (after the task; checked after each of the bot's runs and once at boot), the gateway
    clears the site in the bot's Chromium and drops the row.
- **Sign out** on a Vault row (`POST /api/bots/{id}/site-logins/{login_id}/sign-out`, Linux bots) clears the
  host the same way and removes the row. Forget stays (removes the label only).

**Clearing a site** (`roost/desk/site_data.py`, `Desk.clear_site_data(host)`): the host is validated (a plain
DNS name, no scheme, port, path or IP tricks), then fixed CDP over the keeper's relay: `Storage.getCookies`,
`Network.deleteCookies` for each cookie whose domain is the host or a subdomain of it, and
`Storage.clearDataForOrigin` (`all`) for `https://` and `http://` of the host and of every subdomain those
cookies named. Nothing else is accepted; no shell, no argv.

**Schema v27** (one migration): `stuck_cards.sign_in INTEGER NOT NULL DEFAULT 0`, `site_logins.kept INTEGER NOT
NULL DEFAULT 1`, `site_logins.clear_after_item_id TEXT` (an id, plaintext), and an index on pending clears.

**Routes / tools / fields.** `POST /api/stuck/{id}/open-sign-in`, `POST /api/stuck/{id}/later`, `keep` on
`/clear`, `POST /api/bots/{id}/site-logins/{login_id}/sign-out`; `sign_in` on `StuckCardOut` and the stuck
message body; `kept` on `SiteLoginOut`; the tool `request_sign_in`. Another user's card, bot or login is a 404.

**Password safety (verified).** C3's gate already refuses `type` and `press_key` into a password or one-time-code
box (`secret_field`, `ACT_TEXTS.password`) and clicks on one; this track adds tests for it through the runner.
Take control input goes through `roost/desk/rfb.py`, which never logs or stores key events.

**Risks.** A site keeps state in places CDP's origin clear does not reach (another eTLD+1 SSO host): we clear
the host and its subdomains only, and say so in the result. A sleeping computer is woken to clear (a room
slot). A failed clear keeps the row and retries after the next run.

## Guards (review fixes)

- `request_sign_in` in a tainted or link-guarded run asks only for the open page's site or one in the run's link scope (as `open_page` under D4), so web content can't choose the page you sign in on.
- Give it back on a Sign-in card must say whether to keep the login (`keep`; 400 without it, the card stays open). The card's Holding view asks "Keep me signed in on this computer?" like I'm done does.
- "No, this time" waits for the whole task: nothing is cleared while the continue item is queued or running, the bot has other queued work, or it has an open Ask, Proposal, options or Stuck card.
- Open sign-in and the clear follow the bot's current computer: a bot now on Mac Brave gets a 400 on Open sign-in and keeps its pending row (no Linux computer is started); a gone bot's pending rows are dropped.
