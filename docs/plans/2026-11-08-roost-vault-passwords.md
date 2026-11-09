# Vault: passwords (owner, 2026-11-08)

> "Vault fields inside chat and save vault in encrypted place where LLM never see but by permission we can use, save
> passwords"

Today a password you type into a Sign-in card is used once and forgotten, and `use_saved_login` depends on each
bot's own Chromium remembering it. This adds **Vault: passwords**: Roost keeps your site passwords sealed, the model
never sees one, and a bot may have Roost type one into a sign-in page only with your Yes (or your standing "Always
for this site").

Decisions made overnight by Claude Code (the owner may change them):

- **V1. Where they live:** schema v44 `vault_passwords`: `id`, `user_id`, `host` (sealed, AAD
  `vault_passwords:host`) with `host_key` (two-step keyed HMAC, as `vault/store.host_key`), `username` (sealed) with
  `username_key`, `password` (sealed, AAD `vault_passwords:password`), `always` (0/1, your standing OK for this
  site), `created_at`, `updated_at`, `last_used_at`; `UNIQUE(user_id, host_key, username_key)`; at most
  `VAULT_PASSWORDS_MAX` (200) per user. Saving the same site and user name again replaces the password.
- **V2. Write-only:** no route, tool, event, log, audit row or prompt ever carries a password. `GET` lists the host,
  the user name, `always`, and the dates. There is no "show password".
- **V3. Saving, three ways:**
  1. **The Sign-in card's masked field** gets "Save in Vault" (on by default). Roost reads the user name from the
     page's own sign-in box (`PageTarget.sign_in_box`, its text via `box_text`; empty when there is none) and saves
     it with the host of the card. `POST /api/stuck/{id}/secret` takes `save: bool` (default false for old clients).
     Only a `password` kind is saved, never a one-time code.
  2. **Settings → Vault: passwords:** Add (site, user name, password), the list, Always for this site (a switch),
     Delete.
  3. **In a chat**, the composer's + menu has **Save a password**: the same three fields in a sheet. It posts to the
     Vault API, never to the chat: no message is written, and the bot is not told.
- **V4. Using one:** a Linux bot gets `use_vault_password(index, expect)`: on a sign-in page, the index of the email
  or user name box (or of the password box when the page shows only that). Roost finds your saved login for the
  page's host (exact host, or a saved parent: a login saved for `upwork.com` serves `www.upwork.com`, never the
  reverse). None saved: the result says so and the bot uses `request_sign_in`. Several user names for one site: the
  bot is told the count, and the card lists them to pick from.
- **V5. Permission:** unless that login has **Always**, the run parks on an Ask card: "Sign in to upwork.com with
  your saved password?", the user name as its row, and **Yes · Always for this site · No**. In every mode, every
  chat, clean or tainted. A routine's card waits for the next run as every Ask card does. With Always it fills with
  no card and the chat shows the quiet line "Used your saved password for upwork.com".
- **V6. The fill (on Yes, or at once with Always):** Roost takes the computer's screen lease, reads the live page
  again, and checks its host still matches the saved one (else "The page changed, so I didn't type it"). It types
  the user name into the sign-in box when the page has one and it doesn't already hold it, reading it back, then
  types the password into the one visible password box of the top page (never a box inside another site's frame),
  checking the box is focused first. It presses nothing: the bot clicks Sign in itself. The audit keeps the host
  and the login's id, never a value or a length.
- **V7. What the model sees:** that a saved login exists for the host and how many; after a fill, "Filled the
  user name and password. Click Sign in." It never gets the user name either (it is on the card for you).
- **V8. Never typed elsewhere:** `type` still refuses every password box (the gate's `never`); the only way a
  password reaches a page is V6, and only on its own site.

## As built (2026-11-08, overnight)

Simpler than V4/V5 above, so no client change is needed for the card:

- **The card is a plain Ask card** (floor `secret`): title "Sign in to <site> with your saved password?", rows
  **Site** and **User name**, and the usual **Yes · No**. Its stored call carries the box (`index`, `expect`), the
  login's id, the site and the user name; Yes re-reads the page, needs the same box on a page of the same site, and
  the login to still be that site and user name (`roost/computer_use/vault_login.py`, `vault_rerun`).
- **Always for this site** is a switch on the login in Settings (`PATCH ... {always}`), not a third card button.
- **Several user names for one site:** the one used last (else the first saved) is the one the card names; you can
  delete the others in Settings. No picker on the card.
- **The audit** row is `vault_login_typed` with the site and the login's id only.
- `use_saved_login` (the browser's own saved password) stays as it was; the sign-in note names
  `use_vault_password` first.

## API

- `GET /api/vault/passwords` → `[{id, host, username, always, created_at, updated_at, last_used_at}]`
- `POST /api/vault/passwords` `{host, username, password, always?}` → 201 the row (no password). Host is normalised
  (`vault/models.normalise_host`); bad host, empty password or a value over `VAULT_FIELD_MAX` → 422 that never
  echoes the value. Full → 409.
- `PATCH /api/vault/passwords/{id}` `{password?, always?}` → the row.
- `DELETE /api/vault/passwords/{id}` → 204. Another user's id → 404.
- `POST /api/stuck/{id}/secret` gains `save: bool`.
- (Not built, see "As built": the Ask card is unchanged.)

## Server modules

`roost/vault/passwords.py` (store: seal, open, list, save, patch, delete, find for a host; the keys),
`roost/vault/password_fill.py` (V6), `roost/computer_use/vault_tool.py` (the tool spec and V4/V5), the routes in
`roost/gateway/routes/vault_passwords.py`, the save in `roost/signin/secret_entry.py`.

## Clients

Web: `web/src/components/settings/VaultPasswordsList.tsx` (as `PaymentCardsList.tsx`), the add sheet (shared with
the chat's + menu), the Sign-in card's Save in Vault switch, the Ask card's three buttons and user name picker.
Phone: the same in `mobile/lib/vault/`, Settings, the + menu, `secret_field.dart` and `approval_cards.dart`.
