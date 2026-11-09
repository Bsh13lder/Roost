"""``use_vault_password`` (owner, 2026-11-08, docs/plans/2026-11-08-roost-vault-passwords.md V4-V8).

On a sign-in page inside the run's site fence, the bot names the email or user name box (or the password box when
the page shows only that). Roost finds the owner's saved login for the page's site (Vault: passwords). Unless that
login has Always for this site, the run parks on an Ask card that names the site and the user name; Yes runs the
stored call (``vault_rerun``), which resolves the page again, checks the same box and the same login, and has Roost
type the login into the page (``roost/vault/password_fill.py``). The model never sees the user name or the
password: its results say only what happened. A ``ComputerUse`` mixin; a free screen act (``CU_FREE_ACT_TOOLS``)."""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Final

from roost.approvals.models import ArgRow, PendingCall, StepOutcome
from roost.approvals.texts import NEEDS_YOUR_OK_TEXT
from roost.computer_use import session as loop
from roost.computer_use.models import ActResolution, ClickIn, PageTarget, VaultLoginIn, resolution_to_json, same_target
from roost.computer_use.outcome import CuOutcome
from roost.computer_use.texts import CHANGED_TEXT
from roost.desk.stuck import host_of_url
from roost.talk.gate import GateContext
from roost.vault.models import normalise_host
from roost.vault.password_fill import FillRefused, fill_login
from roost.vault.passwords import PasswordNotFound, SavedLogin, VaultPasswordStore, host_serves

logger = logging.getLogger(__name__)

VAULT_TOOL: Final = "use_vault_password"
_ONE_LINE: Final = "input"
VAULT_AUDIT_ACTION: Final = "vault_login_typed"
SITE_ROW, USER_ROW = "site", "username"
VAULT_ROW_LABELS: Final = {SITE_ROW: "Site", USER_ROW: "User name"}
VAULT_HIDDEN_KEYS: Final = frozenset({"index", "expect", "login_id"})
CARD_TITLE: Final = "Sign in to {host} with your saved password?"
FILLED_TEXT: Final = "Filled the user name and password. Click Sign in next, then look."
FILLED_LINE: Final = "Used your saved password for {host}"
NO_LOGIN_TEXT: Final = "There is no saved login for {host} in Vault: passwords. Call request_sign_in."
NOT_A_BOX_TEXT: Final = ("Refused: use_vault_password needs the one-line email or user name box of a sign-in form, "
                         "or its password box.")
NO_PASSWORD_BOX_TEXT: Final = "Refused: this page has no password box, so it is not a sign-in form."
OFF_FENCE_TEXT: Final = "Refused: {host} is not a site you may use in this task."
LOGIN_GONE_TEXT: Final = "That saved login is gone from Vault: passwords, so I didn't type it."


def _pick(logins: tuple[SavedLogin, ...]) -> SavedLogin:
    """The login used last on this site, or else the first saved."""
    used = [login for login in logins if login.last_used_at]
    return max(used, key=lambda login: login.last_used_at or "") if used else logins[0]


def _user_box(target: PageTarget | None) -> bool:
    """A one-line sign-in box of the top page: never a text area, a contenteditable or another site's frame
    (security review M1: the user name must not land where the page shows it back to the bot)."""
    return (target is not None and target.sign_in_box and target.tag == _ONE_LINE and not target.secret_field
            and not target.cross_origin_frame)


def _box_ok(target: PageTarget | None) -> bool:
    if target is None or target.card_field or target.cross_origin_frame:
        return False
    return target.secret_field or _user_box(target)


def _refused(r: ActResolution) -> bool:
    """A click on a password box is refused as an act; here nothing clicks it as one (the fill picks that box)."""
    return bool(r.refusal) and not (r.target is not None and r.target.secret_field)


def _fills_at_once(login: SavedLogin, page_host: str) -> bool:
    """Always fills with no card only on the exact site saved; a sub-site (a shared domain's tenant) asks
    (security review M2)."""
    return login.always and normalise_host(page_host) == login.host


class VaultLogin:
    """Mixed into ``ComputerUse``: every attribute it reads is the runner's."""

    def _vault(self) -> VaultPasswordStore:
        return VaultPasswordStore(self._run.config)

    async def _vault_login(self, args: VaultLoginIn, ctx: GateContext) -> CuOutcome:
        await self._ready()
        self._require_hands()
        aimed, why = await self._aimed(args)
        if why:
            return CuOutcome(why)
        page = self._desk.page()
        host = host_of_url(await page.url())
        refusal = await self._vault_refusal(aimed, host)
        if refusal is not None:
            return CuOutcome(refusal)
        logins = await self._vault().for_host(self._run.user_id, host)
        if not logins:
            return CuOutcome(NO_LOGIN_TEXT.format(host=host))
        login = _pick(logins)
        r = await self.resolve("click", ClickIn(index=args.index, expect=args.expect), aimed=aimed)
        if r.target is None or r.covered_by or _refused(r):
            return CuOutcome(CHANGED_TEXT)
        if _fills_at_once(login, host):
            return await self._vault_fill_now(r, login, host)
        if ctx.approval is None or not ctx.approval.cards:   # only a run that can show a card may ask (L1)
            return CuOutcome(NEEDS_YOUR_OK_TEXT)
        return CuOutcome("", parked=self._vault_card(args, r, login, host))

    async def _vault_refusal(self, aimed: PageTarget | None, host: str) -> str | None:
        if not _box_ok(aimed):
            return NOT_A_BOX_TEXT
        if self._fence is None or not host or not self._fence.allows(host):
            return OFF_FENCE_TEXT.format(host=host or "this site")
        if not (await self._desk.page().facts()).password_field:
            return NO_PASSWORD_BOX_TEXT
        return None

    def _vault_card(self, args: VaultLoginIn, r: ActResolution, login: SavedLogin, host: str) -> PendingCall:
        """Every stored argument is shown or is a fixed hidden key: the site and user name rows are what Yes uses."""
        arguments = {"index": args.index, "expect": args.expect, "login_id": login.id, SITE_ROW: login.host,
                     USER_ROW: login.username}
        rows = tuple(ArgRow(key, label, str(arguments[key])) for key, label in VAULT_ROW_LABELS.items())
        return PendingCall(tool=VAULT_TOOL, arguments=arguments, topic="browsing", title=CARD_TITLE.format(host=host),
                           floor="secret", rows=rows, act=resolution_to_json(r))

    async def _vault_fill_now(self, r: ActResolution, login: SavedLogin, host: str) -> CuOutcome:
        outcome = await self._vault_type(r, login.id, login.host, login.username)
        if outcome.ok:
            await self._announce(FILLED_LINE.format(host=host))
            return CuOutcome(outcome.text, url=await self._desk.page().url())
        return CuOutcome(outcome.text)

    async def _vault_type(self, r: ActResolution, login_id: str, site: str, username: str) -> StepOutcome:
        """Type the saved login (it must still be for ``site`` and ``username``) into this page."""
        store = self._vault()
        try:
            secret = await store.secret(self._run.user_id, login_id)
        except PasswordNotFound:
            return StepOutcome(False, LOGIN_GONE_TEXT)
        if secret.host != site or secret.username != username:
            return StepOutcome(False, LOGIN_GONE_TEXT)
        page = self._desk.page()
        user_box = r.target if _user_box(r.target) else None
        inputs = SimpleNamespace(send_input=self._input)     # hands checked, and every sent input counted (L3)
        try:
            await fill_login(page, inputs, user_box, secret)
        except FillRefused as exc:
            return StepOutcome(False, exc.detail)
        finally:
            self.state = loop.after_open(self.state)      # the page may have moved: the next act looks first
        await store.mark_used(self._run.user_id, login_id)
        await self._gate.record_approved(self._run.user_id, self._run.bot_id, VAULT_AUDIT_ACTION,
                                         {"site": secret.host, "login_id": login_id}, reason="approved",
                                         tainted=True)
        logger.info("use_vault_password for bot %s on %s: filled", self._run.bot_id, secret.host)
        return StepOutcome(True, FILLED_TEXT)

    async def vault_rerun(self, step: PendingCall, stored: ActResolution) -> StepOutcome:
        """Your Yes: the same box on a page of the same site, then the same login."""
        arguments = step.arguments
        args = ClickIn(index=int(arguments["index"]), expect=str(arguments["expect"]))
        fresh = await self.resolve("click", args, pinned=stored.target)
        host = host_of_url(await self._desk.page().url())
        site = str(arguments[SITE_ROW])
        if not same_target(stored, fresh) or _refused(fresh) or not host_serves(site, host):
            return StepOutcome(False, CHANGED_TEXT, tainted=True)
        return await self._vault_type(fresh, str(arguments["login_id"]), site, str(arguments[USER_ROW]))
