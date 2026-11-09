# The Pay card and Vault: cards (owner, 2026-11-05)

> Owner: "when it arrives to the card page it shows me fields in chat, after my card details save in a secret
> encrypted vault and it asks always CVC". Later (not this plan): an Approved purchase with a limited virtual card.

## Goal

In your own chat a bot carries a purchase to the site's payment step by itself (since 99e6679 only paying asks).
There its click on Pay parks on a **Pay card**: the site, the button, the total it read, and, when the page holds
card boxes, fields for the card. You fill them (or pick a saved card and type only the CVC) and tap Pay. Roost's own
code types the card into the page's boxes and then clicks the same Pay button. **The model never sees, stores or
types a card number, expiry or CVC.**

## Rules (fixed)

- P1. Card boxes are secret boxes. A box whose `autocomplete` is `cc-number`, `cc-exp`, `cc-exp-month`,
  `cc-exp-year`, `cc-csc`, `cc-name` (`cc-type` is a brand list, not secret), or whose name/id/label reads card number / CVC / CVV / expiry
  (EN + ES), is `PageTarget.card_field` (its part). The bot never types there (as a password box), it is never a
  draft row, never read back into a card, never captured by Teach, and its value is never in the look summary.
- P2. Only a `spend` click in your own chat (`owner_chat_run`) parks on a Pay card. Routines, handoffs and rooms
  are unchanged (their hard floor).
- P3. The card shows fields only for the parts the page has (number, expiry, CVC, name). A saved card fills all
  but the CVC. **The CVC is never stored** (not in the vault, steps, audit, events, logs).
- P4. Card data travels only on `POST /api/approvals/{id}/pay`, a hand-validated body (`extra="forbid"`, no
  FastAPI 422 echo, as `SecretIn`): `{card_id?, number?, exp?, name?, cvc, save: bool}`. Luhn and format checks
  answer with fixed words. Nothing about the values is logged; the audit keeps the parts typed and last 4 only.
- P5. Pay re-resolves the page: same host as the card, the same Pay control (`same_target`, a changed total
  fails, as today), the card boxes still there and empty or holding what Roost typed. Then for each part: click
  the box, re-read focus (same node, `card_field` of that part), type on stdin through roost-input, read back only
  the **length** of digits. Then the stored Pay click runs. One lease for the whole fill (`pay:{card_id}`); your
  Take control stops it.
- P6. **Vault: cards** (schema v42 `payment_cards`): number, expiry, name, brand and last 4 sealed `enc:v2`
  (`payment_cards:<col>`), a keyed-HMAC `number_key` unique per user, `created_at`, `last_used_at`. List shows
  brand and last 4 only; Delete removes it. No route ever returns a number or expiry.
- P7. Screens: the look's mask already greys field boxes; the Pay card's crop greys card boxes too. A
  `send_screenshot` after a fill is refused while card boxes hold text.
- P8. Payment frames (Stripe, Adyen, Braintree): card boxes inside a cross-origin frame can't be read. v1 fills
  only boxes in the page's own frame (a redirect checkout such as Redsys is the page's own frame). For a framed
  card box the Pay card says "This site's card box is protected: Take control to type your card, then Give it
  back" and offers Take control. Framed filling (OOPIF attach) is a later step.

## Pieces

1. `roost/desk/page_targets.py`: read card parts (`card_part`) from autocomplete, name, id, label, placeholder;
   `PageTarget.card_field: str` ("" or the part). `resolve.py` refuses typing there (P1); `runner_typing`,
   `teach/capture`, `owner_words/quote` skip them.
2. `roost/payments/`: `cards.py` (store, P6), `checks.py` (Luhn, expiry, CVC, brand), `fill.py` (P5),
   `texts.py`. Migration v42.
3. Approvals: `ApprovalCardOut.pay` (the card's parts found on the page and the saved cards' brand and last 4),
   built when the stored act's class is `spend`; `POST /api/approvals/{id}/pay` (P4); Don't pay answers No.
4. Web: `PayCard.tsx` (fields with `autocomplete="cc-*"`, a saved-card picker, Save this card, the total row),
   Vault: cards on Settings. Phone: `pay_card.dart`, Vault: cards on Settings.
5. Docs: CLAUDE.md map line; this plan.

## Tests (first)

Card part detection (EN/ES, autocomplete, CVC vs code boxes); the bot can't type into a card box; drafts and
Teach skip card boxes; the pay route refuses a bad Luhn, a closed card, another user's card (404), a held computer,
a changed Pay button; the fill types each part once and then clicks Pay; save stores a sealed card without CVC;
nothing of the values appears in audit, events, logs (caplog) or the message body; a routine's spend click still
refuses.

## As built (2026-11-06)

- P1: `roost/desk/card_names.py` (`card_part`); a card box is also `secret_field`, so every place that skips a secret
  box (drafts, Teach, owner words, auto-review) skips it. Expiry and name words count only beside a card word. The
  look marks it "card box", and typing there is refused with `ACT_TEXTS.card`.
- The Pay card's fields are read live: `GET /api/approvals/{id}/pay` (`PayEntry.fields`) gives the parts the page
  asks (number · exp · name · cvc), a Take-control reason (a framed card box, or an expiry picked from a list) and
  your saved cards. `ApprovalCardOut.pay` marks a Pay card (`roost/payments/pay_card.py`).
- P5: `PayEntry.pay` fills under the lease `pay:<card>`, reads each box back (digits, or the name), audits
  `card_typed` with the parts and last 4, then answers the card Yes, whose re-run clicks only the same Pay button.
  A page with no card boxes just answers Yes.
- P7: `look` already greys every field; the card's button picture (`resolve._crop`) greys secret and card boxes.
- Web: `PayCard.tsx`, Settings → Vault: cards (`PaymentCardsList.tsx`). Phone: `chat/cards/pay_card.dart`,
  Settings → Vault: cards (`payments/payment_cards_screen.dart`).
- Not yet: list boxes (a `<select>` expiry) and framed card boxes fall back to Take control.
