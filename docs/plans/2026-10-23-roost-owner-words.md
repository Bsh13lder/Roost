# Your words count (owner decisions W1–W4, 2026-10-23)

Chief's Upwork chat (2026-10-23) showed the owner saying "check the chats" or "ok" and still getting Ask cards.
The owner wants Grok's feel: your own words are an approval. Payments still ask.

## Decisions

- **W1. A typed yes answers the card.** In a bot's chat, when exactly one Ask card waits there (an approval card of
  kind `ask` that is not an options card; never a Proposal, an options card or a Stuck/Sign-in card), a message
  that is only a plain yes (`OWNER_YES_WORDS`, English and Spanish, at most `OWNER_ANSWER_MAX_WORDS` words,
  punctuation and emoji aside) is the card's Yes, and a plain no (`OWNER_NO_WORDS`) is its No. It goes through the
  very path of the card's button (`ApprovalService.answer`, the same audit, the same `Yes: …` line and
  `card_answer` item). Your message still shows in the chat. With two or more cards, or any other words, the
  message goes the usual steer/queue way. The post answers `status: "steered"` (clients show nothing special) and
  `answered_card` with the card's id.
- **W2. Asked in your own words.** A hard-floor act on the page (`commit_click` of class send, submit, accept or
  delete, or `typed_text`) runs with no card when the bot quotes your request in the act's `owner_words`
  argument and two checks pass:
  1. the quote is really yours: after whitespace and NFC are forgiven it is a whole message or line of one of your
     last `OWNER_WORDS_MESSAGES_MAX` (3) own, untainted messages in this chat, or at least
     `OWNER_WORDS_MIN_WORDS` (3) whole words inside one. Bot replies, cards, tool results and pages are never
     sources. This is checked when the act is resolved (`ActResolution.owner_words`, empty when it failed);
  2. the Fable check (`roost/owner_words/check.py`, Fable 5.1 on the worker, the standing check's pattern) reads
     your quote, the act's class, the host, the control's words and any typed text as escaped data, and only an
     exact `fits` lets it run.
  Then the verdict is `do` with reason `owner_words`, audited like every decision, and the chat's step line ends
  with "(you asked)". Anything else falls back to the usual Ask card. Taint does not block it (your words are
  the authority), but only a run that may show cards (your own chat) can use it: routines, handoffs and rooms
  never do.
- **W3. Payments still ask.** Spend, account changes (sign up, sign out, password, email, plan), unknown controls,
  cross-origin frames, contact details and secrets are never covered by your words.
- **W4. Never stays never.** Password and code boxes, file pickers, points outside the page and links or forms off
  the site fence (`new_site`) are judged exactly as before.

## Files

- `roost/approvals/typed_answer.py`: `typed_answer(text)` (pure) and `answer_by_words` (finds the one open card).
- `roost/gateway/routes/threads.py`: `post_message` tries `answer_by_words` after storing your message.
- `roost/owner_words/`: `constants.py`, `quote.py` (pure: the quote rule and which acts it may cover),
  `check.py` (the Fable check), `guard.py` (`OwnerWordsGuard.confirm`).
- `roost/computer_use/models.py`: `owner_words` on `ClickIn`, `TypeIn`, `PressKeyIn` and `ActResolution`.
- `roost/computer_use/runner.py`: `resolve` checks the quote against your messages.
- `roost/computer_use/gate_rules.py`: `judge_act` answers `owner_words` for a covered floor act; `roost/talk/gate.py`
  confirms it with the guard (any failure is the floor's ask).
- `roost/computer_use/tool_specs.py` and the computer-use prompt: one line about `owner_words`.
- `roost/llm/scripted_worker.py`: the scripted check (`fits` when the quote names the control's words or holds the
  typed text).

## W5. An address you didn't name asks once (owner, 2026-10-23)

Gela refused WhatsApp Web twice ("the address wasn't in one of your own messages") and told the owner to type the
link. Now (`roost/talk/new_site.py`):

- A site you name in words (`NAMED_SITES`, WhatsApp and "whatsup" included) or link, a link on a page already
  read for the request and the bot's `web_search` results still open directly (M1 D4's `LinkScope`).
- Any other address, in a run that can show you a card, parks on an **Open card**: "Open web.whatsapp.com", the
  site, the whole address and what it does; the buttons are Open · No (web and phone), and a typed "yes" answers
  it (W1). The gate checks the address first (`askable_url`: http(s) only, no credentials, port, backslash,
  local or private host, via `check_url`) and the card stores the canonical address.
- **Open** runs exactly the stored `open_page` (`PageOpens`, audited as `approved`), hands the run that carries on
  that address and its site as link scope, and counts as a new-site approval for the chat, so the computer's site
  fence lets the bot browse that host (`approved_site_hosts` reads an approved Open card's address).
- Nobody watching (a routine, a handoff, a room): the plain refusal, which no longer tells the owner to type the
  link. The bot is told to use the site's real address and never to ask the owner to type a link.
- A card from a tainted run carries the usual "from web content" mark, and the full address is always shown, so a
  page that tries to smuggle data out in an address is plain to see.

## W6 + W7. A fresh run opens any site (owner, 2026-10-24)

Asked "should bots open any site in a fresh task without asking?", the owner said "Yes do that" (W6). Since a run
starts tainted whenever the chat's last `CHAT_TAINT_KEEP` messages hold a tainted reply, W6 rarely applied, so the
owner chose option 2 ("Lets go for 2", W7): your new message counts as a fresh start, for opening sites only. The
rule (`FRESH_RUN_OPENS_ANY_SITE` in `roost/constants.py`):

- **Site-fresh run:** a 1:1 run made only of your own new chat messages (`GateContext.owner_chat`; never a routine,
  a handoff, a room or a card's continue item) that may show cards starts site-fresh (`turn._site_fresh`), whatever
  the chat's older history holds (a tainted reply, a teammate's tainted line, a tainted memory). A claimed message
  that is itself tainted, or survived a crash mid-call, is not fresh. Freshness ends the moment the run itself takes
  in outside content: a page read or looked at, a search, a tainted record or Mac file, a connector answer, a tainted
  helper or teammate answer, a tainted steered message (`ToolRunner.tainted`'s setter clears `site_fresh`).
- **Open any address:** while site-fresh, `open_page` opens any address `askable_url` accepts, at once and with no
  Open card (`roost/talk/gate.py`, verdict `do` with reason `fresh_open`, judged before D4's link guard and audited
  like every decision), and the browser opens the canonical address. An address no card could make safe
  (credentials, a port, a backslash, a scheme other than http(s), a local or private host) is still never opened
  (`UNSAFE_ADDRESS_TEXT`). With outside content in the chat's history (a tainted or link-guarded run), only a
  site's main address (no path, query or fragment, `gate._no_data_in`) skips the card, so an old page's words can't
  carry your data out inside an address; a full address there gets the Open card. A clean run (W6) opens any address.
- **Browse that site:** the site such an open went to (`fresh_site`: its host without `www.`) stays usable for the
  rest of that run only: a `host:` entry joins the link scope, and `ComputerUse.allow_site` adds it to the
  computer's site fence (guards already armed take the wider fence at once). On the computer, every click follows a
  fresh look, and a look ends freshness, so a link or form to any other host keeps the new-site card.
- **What does not change:** the run's ordinary taint rules everything else: the tainted-write rule, `remember` and
  `create_routine` refused, the hard floor (buying, sending, submitting, accepting, deleting, account changes,
  unknown controls, contact details, secrets, password boxes; W2 included; payments still ask). Once the run has
  read a page, any other new site goes back to the Open card or the new-site card; a page never widens the fence.
  Routines, handoffs, rooms and card answers are judged exactly as before.

## W8–W11. What you said in the chat counts (owner, 2026-10-31)

The Upwork run of 2026-10-31 asked three times for one "Apply now" after the owner wrote "check that job good and
send proposel": "apply" was a submit word, the bot quoted the owner only once (and the check said ask), and each
approved click that left the page in place asked again. The owner: "Yes do", and their chat words should work
like Claude Code's: if they told the bot to do it, it fits, the Upwork Connects send included.

- **W8. "Apply now" opens a form.** `FORM_OPEN_WORDS` (apply, apply now, aplicar, postular, postularse) are browsing
  outside a POST form (`roost/computer_use/commit_words.py`); a POST form's submit stays submit by its structure.
- **W9. Roost quotes you when the bot forgets.** An act with no `owner_words` takes your newest own, untainted
  message in the chat as its quote (`your_quote`); the Fable check still decides. The check now counts a step on
  the way to what you asked, "check it and send it" words, and spending a site's own credits for what you asked
  (Upwork Connects) as `fits`; paying money (a card, a checkout, a purchase) still asks, and spend-class buttons
  ("Buy Connects", "Pay") never reach the check (W3).
- **W10. A Yes covers the same button again.** A click on the very control of a card you approved in this chat in
  the last `OWNER_AGAIN_WINDOW_S` (15 min), on the same page (`same_target`), runs with reason `approved`
  (`roost/owner_words/again.py`, `ActResolution.approved_again`). Only submit and accept: a second Send, Pay or
  Delete would do it twice, so those still ask.
- **W11. The check's answer is logged.** A "no" logs `owner words check answered: ask|other (action … on <host>)`
  at WARNING; the reply and your words are never logged.
