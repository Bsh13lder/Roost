"""``use_vault_password`` (owner, 2026-11-08, docs/plans/2026-11-08-roost-vault-passwords.md V4-V8): on a sign-in
page of a site the owner saved a login for, the bot asks; on the owner's Yes (or at once with Always for this site)
Roost types the user name and password into the page itself. The model never sees either. No real model."""

from __future__ import annotations

import re

import pytest

from roost.approvals.rows import with_rows
from roost.computer_use.fence import SiteFence
from roost.computer_use.gate_rules import judge_act
from roost.computer_use.tool_specs import cu_tools_for
from roost.config import load_config
from roost.constants import CU_FREE_ACT_TOOLS, CU_TOOLS
from roost.db.connection import init_db
from roost.desk.fake_cu import FakeScreenState, fake_target, script
from roost.talk.instructions import SIGN_IN_PAGE_NOTE
from roost.talk.tool_catalog import CATALOG
from roost.vault.passwords import NewLogin, VaultPasswordStore
from cu_run_helpers import ctx, make_cu_rig, step

PASSWORD = "hunter2-very-secret"
USER = "ana@mail.example"
_FORM = dict(form_method="post", form_submit_text="Sign in")
_CONTROLS = (
    fake_target("field", "Email", 100, 100, width=300, tag="input", input_type="email", sign_in_box=True, **_FORM),
    fake_target("field", "Password", 100, 160, width=300, tag="input", input_type="password", secret_field=True,
                **_FORM),
    fake_target("button", "Sign in", 100, 220, tag="button", is_form_submit=True, **_FORM),
)


def _login_page(host: str):
    return script([
        ("login", FakeScreenState(url=f"https://{host}/login", title="Sign in", targets=_CONTROLS,
                                  text="Sign in to your account", password_field=True)),
        ("moved", FakeScreenState(url="https://evil.example/login", title="Sign in", targets=_CONTROLS,
                                  text="Sign in to your account", password_field=True)),
    ])


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


async def _rig(cfg, host: str = "login.example", *, saved_for: str | None = "login.example", always: bool = False,
               message: str | None = None):
    rig = await make_cu_rig(cfg, message or f"Sign in to {host} and check my bookings", screen=_login_page(host))
    if saved_for is not None:
        store = VaultPasswordStore(cfg)
        saved = await store.save(rig.user_id, NewLogin(host=saved_for, username=USER, password=PASSWORD))
        if always:
            await store.patch(rig.user_id, saved.id, password=None, always=True)
    return rig


def _index(look_text: str, label: str) -> int:
    found = re.search(rf"\[(\d+)\][^\n]*(?:\"|&quot;){label}(?:\"|&quot;)", look_text)
    assert found, look_text
    return int(found.group(1))


async def _use(rig, label: str = "Email"):
    cu = rig.computer()
    seen = await step(cu, "look")
    return cu, await step(cu, "use_vault_password", index=_index(seen.text, label), expect="the login fills")


def _never_shown(rig, *texts: str) -> None:
    for text in texts:
        assert PASSWORD not in text and USER not in text
    assert PASSWORD not in " ".join(rig.lines) and USER not in " ".join(rig.lines)


async def test_it_asks_first_and_the_card_names_the_site_and_your_user_name(cfg):
    rig = await _rig(cfg)
    _, outcome = await _use(rig)
    card = outcome.parked
    assert card is not None and rig.page.typed_lengths == ()
    assert card.title == "Sign in to login.example with your saved password?"
    assert [(row.key, row.value) for row in card.rows] == [("site", "login.example"), ("username", USER)]
    assert PASSWORD not in repr(card)
    assert with_rows(card) == card                      # what the card shows is what Yes runs
    _never_shown(rig, outcome.text)


async def test_yes_types_the_login_into_the_page_and_presses_nothing(cfg):
    rig = await _rig(cfg)
    cu, outcome = await _use(rig)
    await cu.close()                                    # the run parked: it lets go of the screen
    done = await rig.computer("run-2").rerun(outcome.parked)
    assert done.ok, done.text
    assert rig.page.typed_lengths == (len(USER), len(PASSWORD))
    assert "Click Sign in" in done.text
    _never_shown(rig, done.text)


async def test_always_for_this_site_fills_with_no_card(cfg):
    rig = await _rig(cfg, always=True)
    _, outcome = await _use(rig)
    assert outcome.parked is None and rig.page.typed_lengths == (len(USER), len(PASSWORD))
    assert "Click Sign in" in outcome.text
    _never_shown(rig, outcome.text)


async def test_a_sub_site_is_served_by_its_parents_login_but_always_asks_there(cfg):
    # security review M2: Always fills only on the exact site saved; a sub-site (a shared domain's tenant) asks
    rig = await _rig(cfg, "accounts.login.example", saved_for="login.example", always=True,
                     message="Sign in to accounts.login.example")
    cu, outcome = await _use(rig)
    assert outcome.parked is not None and rig.page.typed_lengths == ()
    assert outcome.parked.title == "Sign in to accounts.login.example with your saved password?"
    await cu.close()
    done = await rig.computer("run-2").rerun(outcome.parked)
    assert done.ok and rig.page.typed_lengths == (len(USER), len(PASSWORD)), done.text


async def test_a_run_that_cannot_show_a_card_is_told_it_needs_your_ok(cfg):
    # security review L1: a handoff, room or routine run without Always never parks a card
    rig = await _rig(cfg)
    cu = rig.computer()
    seen = await step(cu, "look")
    outcome = await step(cu, "use_vault_password", ctx(cards=False), index=_index(seen.text, "Email"),
                         expect="the login fills")
    assert outcome.parked is None and rig.page.typed_lengths == () and "OK" in outcome.text


async def test_a_text_area_or_framed_box_never_takes_the_user_name(cfg):
    # security review M1: only a one-line sign-in box (or the password box) may be named
    area = fake_target("field", "Notes", 100, 280, width=300, tag="textarea", sign_in_box=True, **_FORM)
    framed = fake_target("field", "Login", 100, 340, width=300, tag="input", input_type="text", sign_in_box=True,
                         cross_origin_frame=True, **_FORM)
    page = script([("login", FakeScreenState(url="https://login.example/login", title="Sign in",
                                              targets=(*_CONTROLS, area, framed), password_field=True))])
    rig = await make_cu_rig(cfg, "Sign in to login.example", screen=page)
    await VaultPasswordStore(cfg).save(rig.user_id, NewLogin(host="login.example", username=USER, password=PASSWORD))
    for label in ("Notes", "Login"):
        cu = rig.computer(f"run-{label}")
        seen = await step(cu, "look")
        outcome = await step(cu, "use_vault_password", index=_index(seen.text, label), expect="the login fills")
        assert outcome.text.startswith("Refused") and outcome.parked is None, label
        await cu.close()
    assert rig.page.typed_lengths == ()


async def test_naming_the_password_box_types_only_the_password(cfg):
    rig = await _rig(cfg, always=True)
    _, outcome = await _use(rig, "Password")
    assert rig.page.typed_lengths == (len(PASSWORD),), outcome.text


async def test_no_saved_login_says_so_and_points_at_request_sign_in(cfg):
    rig = await _rig(cfg, saved_for=None)
    _, outcome = await _use(rig)
    assert outcome.parked is None and "request_sign_in" in outcome.text and rig.page.typed_lengths == ()


async def test_another_sites_login_is_never_used(cfg):
    rig = await _rig(cfg, "evil-login.example", saved_for="login.example", always=True,
                     message="Sign in to evil-login.example")
    _, outcome = await _use(rig)
    assert outcome.parked is None and rig.page.typed_lengths == () and "request_sign_in" in outcome.text


async def test_a_site_outside_the_fence_is_refused(cfg):
    rig = await _rig(cfg, "evil.example", saved_for="evil.example", always=True,
                     message="Please check my bookings on login.example")
    _, outcome = await _use(rig)
    assert outcome.text.startswith("Refused") and rig.page.typed_lengths == ()


async def test_a_yes_on_a_page_that_moved_to_another_site_types_nothing(cfg):
    rig = await _rig(cfg)
    cu, outcome = await _use(rig)
    await cu.close()
    rig.page._go("moved")                               # the tab went to another site before your Yes
    done = await rig.computer("run-2").rerun(outcome.parked)
    assert not done.ok and rig.page.typed_lengths == ()


def test_it_is_a_free_screen_act_offered_only_to_a_linux_computer():
    from types import SimpleNamespace
    assert "use_vault_password" in CU_TOOLS and "use_vault_password" in CU_FREE_ACT_TOOLS
    assert CATALOG["use_vault_password"].kind == "act"
    assert judge_act("use_vault_password", None, ctx(), SiteFence(frozenset({"login.example"}))).decision == "do"
    assert "use_vault_password" in cu_tools_for(SimpleNamespace(computer="linux"))   # type: ignore[arg-type]
    assert "use_vault_password" not in cu_tools_for(SimpleNamespace(computer="mac_brave"))   # type: ignore[arg-type]


def test_the_sign_in_note_points_at_it_before_asking_you():
    assert "use_vault_password" in SIGN_IN_PAGE_NOTE
