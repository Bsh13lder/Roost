"""Owner, 2026-11-05: a bot moves through a site like a human (booking a bus on alsa.es). A dialog over the control it
wants is closed with Escape or the dialog's own close button right away, with no look in between; a click at a
point where nothing is says what is near there and how to aim by number instead."""

from __future__ import annotations

import pytest

from roost.computer_use.models import ActResolution, Box, PageTarget
from roost.computer_use.refusal_keys import refusal_key
from roost.computer_use.session import (
    LOOK_FIRST_TEXT, TAKEN_TEXT, LoopState, after_act, after_look, after_miss, closes_cover, new_step, precheck,
)
from roost.computer_use.texts import POINT_MISS_TEXT
from roost.config import load_config
from roost.db.connection import init_db
from roost.desk import FrontWindow
from roost.desk.fake_cu import FakeScreenState, fake_target, script

from cu_run_helpers import make_cu_rig, step

_MESSAGE = "Book me a bus on www.alsa.es from Madrid to Valencia for Friday"
_DATE = fake_target("button", "Fecha de ida", 560, 500, width=160, tag="button", expands=True)
_SEARCH = fake_target("button", "Buscar billetes", 760, 500, width=160, tag="button")
_CLOSE = fake_target("button", "Cerrar", 600, 200, width=100, tag="button", in_dialog="Tus cookies")
_ACCEPT = fake_target("button", "Aceptar todo y pagar", 720, 200, width=200, tag="button", in_dialog="Tus cookies")
_PAGE = (_DATE, _SEARCH)
ALSA = script([
    ("covered", FakeScreenState(url="https://www.alsa.es/", title="Alsa", targets=(*_PAGE, _CLOSE, _ACCEPT),
                                text="Billetes de autobus", dialog="Tus cookies",
                                on_click={"Cerrar": "open"}, on_key={"Escape": "open"})),
    ("open", FakeScreenState(url="https://www.alsa.es/", title="Alsa", targets=_PAGE, text="Billetes de autobus",
                             on_click={"Fecha de ida": "calendar"})),
    ("calendar", FakeScreenState(url="https://www.alsa.es/", title="Alsa", text="Elige la fecha")),
])


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def rig(cfg):
    return await make_cu_rig(cfg, _MESSAGE, screen=ALSA)


# -- the loop's rules ----------------------------------------------------------------------------------------

def _button(node_id: int, text: str, dialog: str = "") -> PageTarget:
    return PageTarget(node_id=node_id, kind="button", text=text, tag="button", input_type="", box=Box(10, 10, 80, 20),
                      form_method="", form_submit_text="", is_form_submit=False, link_host="", in_dialog=dialog,
                      in_consent=False, cross_origin_frame=False, editable=False, secret_field=False,
                      searchish=False, expands=False)


def _click(target: PageTarget) -> ActResolution:
    return ActResolution(tool="click", url="https://x.example/", host="x.example", target=target,
                         point=target.box.center(), covered_by="", nav_host="", commit="browsing")


def _stale() -> LoopState:
    looked = new_step(after_look(LoopState(run_id="r1"), 0))
    return new_step(after_act(looked, _click(_button(1, "Next")), "page 2"))


def test_escape_needs_no_fresh_look_but_other_keys_do():
    stale = _stale()
    assert precheck(stale, "press_key", 0, {"key": "Escape"}) is None
    assert precheck(stale, "press_key", 0, {"key": "Enter"}) == LOOK_FIRST_TEXT
    assert precheck(stale, "press_key", 0, {"key": "Escape", "index": 3}) == LOOK_FIRST_TEXT
    assert precheck(stale, "click", 0, {"x": 5, "y": 5}) == LOOK_FIRST_TEXT
    assert precheck(stale, "press_key", 1, {"key": "Escape"}) == TAKEN_TEXT     # you took it: still look first


def test_a_covered_miss_lets_only_the_dialogs_own_closer_through():
    missed, last = after_miss(_stale(), "aim", closers=frozenset({42}))
    assert not last and missed.closers == frozenset({42})
    stale = new_step(missed)
    assert precheck(stale, "click", 0, {"target": {"text": "Cerrar"}}) is None   # judged again once resolved
    assert closes_cover(stale, _click(_button(42, "Cerrar", "Tus cookies")))
    assert not closes_cover(stale, _click(_button(43, "Buscar")))
    assert not closes_cover(stale, _click(_button(42, "Pagar ahora", "Tus cookies")))   # it commits: look first
    after = new_step(after_act(stale, _click(_button(42, "Cerrar", "Tus cookies")), "closed"))
    assert after.closers == frozenset()
    plain, _ = after_miss(_stale(), "aim")
    assert plain.closers == frozenset()


# -- the run ---------------------------------------------------------------------------------------------------

async def test_a_covered_click_names_the_dialogs_close_button_and_escape(rig):
    cu = rig.computer()
    await step(cu, "look")
    covered = await step(cu, "click", target={"text": "Fecha de ida"}, expect="the calendar opens")
    assert refusal_key(covered.text) == "covered"
    assert "'Cerrar'" in covered.text and "Escape" in covered.text
    assert "Aceptar todo y pagar" not in covered.text                  # not a closer: it commits
    assert rig.page.state_name == "covered" and rig.desk.inputs == ()


async def test_escape_right_after_a_covered_click_closes_the_dialog(rig):
    cu = rig.computer()
    await step(cu, "look")
    await step(cu, "click", target={"text": "Fecha de ida"}, expect="the calendar opens")
    done = await step(cu, "press_key", key="Escape", expect="the dialog closes")
    assert done.text != LOOK_FIRST_TEXT and rig.page.state_name == "open"
    again = await step(cu, "click", target={"text": "Fecha de ida"}, expect="the calendar opens")
    assert again.parked is None and rig.page.state_name == "calendar"


async def test_the_dialogs_close_button_runs_right_after_a_covered_click(rig):
    cu = rig.computer()
    await step(cu, "look")
    await step(cu, "click", target={"text": "Fecha de ida"}, expect="the calendar opens")
    done = await step(cu, "click", target={"text": "Cerrar"}, expect="the dialog closes")
    assert done.text != LOOK_FIRST_TEXT and rig.page.state_name == "open"


async def test_another_control_right_after_a_covered_click_still_looks_first(rig):
    cu = rig.computer()
    await step(cu, "look")
    await step(cu, "click", target={"text": "Fecha de ida"}, expect="the calendar opens")
    refused = await step(cu, "click", target={"text": "Aceptar todo y pagar"}, expect="x")
    assert refused.text == LOOK_FIRST_TEXT and rig.page.state_name == "covered"
    assert [verb for verb, _, _ in rig.desk.inputs] == []


async def test_a_point_miss_names_what_is_near_and_the_numbers(rig):
    rig.page.state_name = "open"
    cu = rig.computer()
    await step(cu, "look", picture=False)
    missed = await step(cu, "click", x=641, y=600, expect="the calendar opens")
    assert refusal_key(missed.text) == "miss_point"
    assert "(641, 600)" in missed.text and "[1]" in missed.text and "'Fecha de ida'" in missed.text
    assert "index" in missed.text and "picture=false" in missed.text


async def test_a_point_miss_before_any_numbers_still_says_how_to_aim(rig):
    rig.page.state_name = "open"
    cu = rig.computer()
    await step(cu, "look", picture=False)
    cu._marks = type(cu._marks).empty()
    missed = await step(cu, "click", x=20, y=20, expect="x")
    assert missed.text.startswith(POINT_MISS_TEXT.split("{", 1)[0]) and "index" in missed.text


async def test_a_closer_pass_never_lets_a_desktop_click_skip_its_look(rig):
    cu = rig.computer()
    await step(cu, "look")
    await step(cu, "click", target={"text": "Fecha de ida"}, expect="the calendar opens")
    rig.desk.script_front(FrontWindow("other"))                # another app came to the front
    refused = await step(cu, "click", x=600, y=500, expect="x")
    assert refused.text == LOOK_FIRST_TEXT and rig.desk.inputs == ()
