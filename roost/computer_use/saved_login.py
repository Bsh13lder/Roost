"""``use_saved_login`` (owner, 2026-11-05: Wizz Air signed Gela out again and again, "Yes" to letting her sign back in).

On a site the owner signed this bot in to before (a Vault: site login for it, ``roost/vault/``) and inside the run's
site fence, the bot names the email or user name box of a page that has a password box. The runner clicks that box,
presses ArrowDown (the browser's own saved-login list opens) and Enter (the browser fills the login), all through
``roost-input``. Neither Roost nor the model ever sees the password: the browser fills it, and the runner only reads
back whether a password box now holds anything (``roost/desk/saved_login_check.py``). The step is logged with the
host and the outcome alone. A ``ComputerUse`` mixin; the gate lets it run as a free screen act (``CU_FREE_ACT_TOOLS``),
and these guards are its rules."""

from __future__ import annotations

import logging

from roost.computer_use import session as loop
from roost.computer_use.commit_words import is_text_box
from roost.computer_use.models import ClickIn, PageTarget, SavedLoginIn
from roost.computer_use.outcome import CuOutcome
from roost.constants import CU_KEYS, SAVED_LOGIN_POPUP_WAIT_S
from roost.desk import ScreenInput
from roost.desk.stuck import host_of_url
from roost.vault.models import normalise_host
from roost.vault.store import VaultStore

logger = logging.getLogger(__name__)

FILLED_TEXT = "Filled your saved login for {host}. Click Sign in next, then look."
NOT_FILLED_TEXT = "No saved login showed up for {host}. Ask the owner with request_sign_in."
NOT_A_BOX_TEXT = "Refused: use_saved_login needs the email or user name box, never the password box."
NO_PASSWORD_BOX_TEXT = "Refused: this page has no password box, so it is not a sign-in form."
NO_VAULT_TEXT = ("Refused: the owner never signed you in to {host}, so there is no saved login to use. "
                 "Call request_sign_in.")
OFF_FENCE_TEXT = "Refused: {host} is not a site you may use in this task."
MOVED_TEXT = "Something else is there now. Look again."
FILLED_LINE = "Filled the saved login on {host}"


class SavedLogin:
    async def _saved_login(self, args: SavedLoginIn) -> CuOutcome:
        await self._ready()
        self._require_hands()
        aimed, why = await self._aimed(args)
        if why:
            return CuOutcome(why)
        page = self._desk.page()
        host = host_of_url(await page.url())
        refusal = await self._saved_login_refusal(aimed, host)
        if refusal is not None:
            return CuOutcome(refusal)
        r = await self.resolve("click", ClickIn(index=args.index, expect=args.expect), aimed=aimed)
        geo = await page.geometry()
        if r.target is None or r.covered_by or r.refusal or not await self._focus_box(page, r, geo):
            return CuOutcome(MOVED_TEXT)
        x, y = self._pointer_at(r, geo)
        await self._sleep(SAVED_LOGIN_POPUP_WAIT_S)
        for key in ("ArrowDown", "Enter"):
            await self._send(ScreenInput("key", key=CU_KEYS[key], window=geo.window_rect), x, y, "key")
        self.state = loop.after_open(self.state)        # the page may have moved: the next act looks first
        filled = await page.password_filled()
        logger.info("use_saved_login for bot %s on %s: %s", self._run.bot_id, host, "filled" if filled else "none")
        if not filled:
            return CuOutcome(NOT_FILLED_TEXT.format(host=host))
        await self._announce(FILLED_LINE.format(host=host))
        return CuOutcome(FILLED_TEXT.format(host=host), url=await page.url())

    async def _saved_login_refusal(self, aimed: PageTarget | None, host: str) -> str | None:
        """Why this box on this page may not take a saved login, or None."""
        if aimed is None or aimed.secret_field or not is_text_box(aimed):
            return NOT_A_BOX_TEXT
        if self._fence is None or not host or not self._fence.allows(host):
            return OFF_FENCE_TEXT.format(host=host or "this site")
        if not (await self._desk.page().facts()).password_field:
            return NO_PASSWORD_BOX_TEXT
        if not await self._vault_has(host):
            return NO_VAULT_TEXT.format(host=host)
        return None

    async def _vault_has(self, host: str) -> bool:
        site = normalise_host(host)
        logins = await VaultStore(self._run.config).list_for_bot(self._run.user_id, self._run.bot_id)
        return bool(site) and any(normalise_host(login.host) == site for login in logins)
