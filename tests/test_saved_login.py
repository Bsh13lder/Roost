"""``use_saved_login`` (owner, 2026-11-05: Wizz Air signed Gela out again and again): on a site the owner signed in
to before (a Vault: site login for this bot), the bot fills the login from the browser's own saved password, with
ArrowDown and Enter in the email box, so neither Roost nor the bot ever sees the password. It refuses a password
box, a page with no password box, a site with no Vault login and a site outside the fence. No real model."""

from __future__ import annotations

import re

import pytest

from roost.computer_use.fence import SiteFence
from roost.computer_use.gate_rules import judge_act
from roost.computer_use.tool_specs import cu_tools_for
from roost.config import load_config
from roost.constants import CU_FREE_ACT_TOOLS, CU_TOOLS
from roost.db.connection import init_db
from roost.desk.fake_cu import FakeScreenState, fake_target, script
from roost.talk.instructions import SIGN_IN_PAGE_NOTE
from roost.talk.tool_catalog import CATALOG
from roost.vault.store import VaultStore
from cu_run_helpers import ctx, make_cu_rig, step

SECRET = "hunter2-very-secret"
_FORM = dict(form_method="post", form_submit_text="Sign in")
_CONTROLS = (
    fake_target("field", "Email", 100, 100, width=300, tag="input", input_type="email", **_FORM),
    fake_target("field", "Password", 100, 160, width=300, tag="input", input_type="password", secret_field=True,
                **_FORM),
    fake_target("button", "Sign in", 100, 220, tag="button", is_form_submit=True, **_FORM),
)


def _login_page(host: str, *, password_field: bool = True):
    controls = _CONTROLS if password_field else _CONTROLS[:1]
    return script([("login", FakeScreenState(url=f"https://{host}/login", title="Sign in", targets=controls,
                                              text="Sign in to your account", password_field=password_field))])


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


async def _rig(cfg, host: str = "login.example", *, saved: bool = True, vault: bool = True,
               password_field: bool = True, message: str | None = None):
    rig = await make_cu_rig(cfg, message or f"Sign in to {host} and check my bookings",
                            screen=_login_page(host, password_field=password_field))
    rig.page.saved_password = SECRET if saved else None
    if vault:
        await VaultStore(cfg).remember(rig.user_id, rig.bot.id, host, "me@mail.example")
    return rig


def _index(look_text: str, label: str) -> int:
    found = re.search(rf"\[(\d+)\][^\n]*(?:\"|&quot;){label}(?:\"|&quot;)", look_text)
    assert found, look_text
    return int(found.group(1))


async def _use(rig, label: str = "Email"):
    cu = rig.computer()
    seen = await step(cu, "look")
    return cu, await step(cu, "use_saved_login", index=_index(seen.text, label), expect="the password box fills")


async def test_it_fills_the_saved_login_and_says_to_click_sign_in(cfg):
    rig = await _rig(cfg)
    _, outcome = await _use(rig)
    assert "Filled your saved login for login.example" in outcome.text and "Sign in" in outcome.text
    assert rig.page.saved_login_filled is True
    assert SECRET not in outcome.text and SECRET not in " ".join(rig.lines)


async def test_no_saved_password_in_the_browser_says_to_ask_the_owner(cfg):
    rig = await _rig(cfg, saved=False)
    _, outcome = await _use(rig)
    assert "No saved login showed up for login.example" in outcome.text and "request_sign_in" in outcome.text


async def test_a_password_box_is_refused(cfg):
    rig = await _rig(cfg)
    _, outcome = await _use(rig, "Password")
    assert outcome.text.startswith("Refused") and rig.page.saved_login_filled is False


async def test_a_page_with_no_password_box_is_refused(cfg):
    rig = await _rig(cfg, password_field=False)
    _, outcome = await _use(rig)
    assert outcome.text.startswith("Refused") and "password box" in outcome.text


async def test_a_site_with_no_vault_login_is_refused(cfg):
    rig = await _rig(cfg, vault=False)
    _, outcome = await _use(rig)
    assert outcome.text.startswith("Refused") and "never signed you in" in outcome.text
    assert rig.page.saved_login_filled is False


async def test_a_site_outside_the_fence_is_refused(cfg):
    rig = await _rig(cfg, "evil.example", message="Please check my bookings on login.example")
    _, outcome = await _use(rig)
    assert outcome.text.startswith("Refused") and rig.page.saved_login_filled is False


def test_it_is_a_free_screen_act_offered_with_the_other_screen_tools():
    assert "use_saved_login" in CU_TOOLS and "use_saved_login" in CU_FREE_ACT_TOOLS
    assert CATALOG["use_saved_login"].kind == "act"
    verdict = judge_act("use_saved_login", None, ctx(), SiteFence(frozenset({"login.example"})))
    assert verdict.decision == "do"


def test_the_sign_in_note_points_at_it():
    assert "use_saved_login" in SIGN_IN_PAGE_NOTE and "request_sign_in" in SIGN_IN_PAGE_NOTE


def test_only_a_linux_computer_gets_it():
    from types import SimpleNamespace
    assert "use_saved_login" in cu_tools_for(SimpleNamespace(computer="linux"))   # type: ignore[arg-type]
    assert "use_saved_login" not in cu_tools_for(SimpleNamespace(computer="mac_brave"))   # type: ignore[arg-type]


# -- the real page's check, over a fake CDP sender --------------------------------------------------------------

class _Cdp:
    def __init__(self, value: object, *, frame: str = "f1", context: object = 7, fail: str = "") -> None:
        self.value, self.frame, self.context, self.fail = value, frame, context, fail
        self.sent: list[tuple[str, dict]] = []

    async def send(self, method: str, params: dict, *, session_id: str | None = None) -> dict:
        from roost.desk.cdp import CdpReplyError
        self.sent.append((method, params))
        if method == self.fail:
            raise CdpReplyError("gone")
        if method == "Page.getFrameTree":
            return {"result": {"frameTree": {"frame": {"id": self.frame}}}}
        if method == "Page.createIsolatedWorld":
            return {"result": {"executionContextId": self.context}}
        return {"result": {"result": {"value": self.value}}}


async def test_the_page_check_reads_only_a_yes_or_no_in_its_own_world():
    from roost.desk.saved_login_check import LOGIN_WORLD, password_filled
    cdp = _Cdp(True)
    assert await password_filled(cdp, "s1") is True
    world = dict(cdp.sent)["Page.createIsolatedWorld"]
    evaluate = dict(cdp.sent)["Runtime.evaluate"]
    assert world["worldName"] == LOGIN_WORLD and evaluate["contextId"] == 7
    assert ".length > 0" in evaluate["expression"] and "return" not in evaluate["expression"]


@pytest.mark.parametrize("cdp", [
    _Cdp(False), _Cdp("hunter2"), _Cdp(True, frame=""), _Cdp(True, context=None),
    _Cdp(True, fail="Runtime.evaluate"), _Cdp(True, fail="Page.getFrameTree"),
])
async def test_anything_but_a_plain_true_is_not_filled(cdp):
    from roost.desk.saved_login_check import password_filled
    assert await password_filled(cdp, "s1") is False
