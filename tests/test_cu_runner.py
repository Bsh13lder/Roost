"""C3 Task 12: the runner resolves every act from the page, the gate judges that, and only a "do" touches the
screen (move, check the node under the pointer again, then click / type / press)."""

from __future__ import annotations

import pytest

from roost.approvals.texts import NEEDS_YOUR_OK_TEXT, PARKED_TEXT
from roost.computer_use.gate_rules import ACT_TEXTS
from roost.computer_use.lines import act_line
from roost.computer_use.models import ActResolution, Box
from roost.computer_use.runner import WOKE_LOOK_FIRST_TEXT, MOVED_TEXT
from roost.computer_use.session import BUSY_TEXT, LOOK_FIRST_TEXT, TAKEN_TEXT
from roost.config import load_config
from roost.db.connection import init_db
from roost.desk.fake_cu import fake_target
from roost.llm.types import SCREENSHOT_SHOWN
from roost.talk.instructions import CONTROL_HELD_TEXT

from cu_run_helpers import ctx, make_cu_rig, run_step, step


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


# Your message with no site named: the fake shop is not a trusted site, so typing there still asks.
_OFF_FENCE = "Please find wool socks and put a note: blue wool socks size 42"


@pytest.fixture
async def rig(cfg):
    return await make_cu_rig(cfg)


async def test_a_browsing_click_lands_and_announces_clicked_apply(rig):
    cu = rig.computer()
    looked = await step(cu, "look")
    assert looked.looked and SCREENSHOT_SHOWN in looked.text and cu.newest_image()
    done = await step(cu, "click", target={"text": "Jobs"}, expect="the jobs list shows")
    assert rig.page.state_name == "jobs"
    assert [verb for verb, _, _ in rig.desk.inputs] == ["move", "click"]
    assert "Clicked 'Jobs'" in rig.lines and "Address: https://shop.example/jobs" in done.text
    # The line names the control as the page reads it ("Apply" itself is a committing word, so it asks first).
    apply = fake_target("button", "Apply", 10, 10)
    r = ActResolution("click", "https://x.example/", "x.example", apply, (80, 28), "", "", "submit")
    assert act_line("click", r, {}) == "Clicked 'Apply'"


async def test_an_act_before_any_look_is_refused(rig):
    cu = rig.computer()
    assert (await step(cu, "click", target={"text": "Jobs"}, expect="jobs")).text == LOOK_FIRST_TEXT
    assert rig.desk.inputs == ()


async def test_something_moved_under_the_pointer_is_not_clicked(rig, monkeypatch):
    cu = rig.computer()
    await step(cu, "look")
    other = fake_target("button", "Delete account", 450, 100, tag="button")

    async def moved(x: int, y: int):
        return other

    monkeypatch.setattr(rig.page, "node_at", moved)
    done = await step(cu, "click", target={"text": "Jobs"}, expect="jobs")
    assert done.text == MOVED_TEXT
    assert [verb for verb, _, _ in rig.desk.inputs] == ["move"] and rig.page.state_name == "shop"


async def test_typing_your_own_words_types_them(rig):
    cu = rig.computer()
    await step(cu, "look")
    await step(cu, "click", target={"text": "Note"}, expect="the note box is focused")
    typed = await step(cu, "type", text="blue wool socks size 42", source={"from": "message"}, expect="note saved")
    assert rig.desk._screen_page.pasted_lengths == (23,) and rig.page.state_name == "noted"
    assert "Typed into 'Note' (23 characters)" in rig.lines
    assert "blue wool socks" not in typed.text


async def test_typing_made_up_text_needs_no_card(cfg):
    rig = await make_cu_rig(cfg, _OFF_FENCE)       # owner, 2026-11-03: typing never asks, on any site
    cu = rig.computer()
    await step(cu, "look")
    await step(cu, "click", target={"text": "Note"}, expect="focused")
    done = await step(cu, "type", text="please send me a free sample", source={"from": "message"}, expect="saved")
    assert done.parked is None and rig.desk._screen_page.pasted_lengths == (len("please send me a free sample"),)


async def test_typing_an_email_you_never_gave_asks_with_the_full_text(cfg):
    rig = await make_cu_rig(cfg, _OFF_FENCE)
    cu = rig.computer()
    await step(cu, "look")
    await step(cu, "click", target={"text": "Note"}, expect="focused")
    asked = await step(cu, "type", text="write to ana@example.com", source={"from": "message"}, expect="saved")
    assert asked.parked is not None and asked.parked.floor == "contact"
    rows = {row.label: row.value for row in asked.parked.rows}
    assert rows["Text"] == "write to ana@example.com" and rows["Field"] == "Note"
    assert rig.desk._screen_page.pasted_lengths == ()


async def test_typing_an_email_from_your_own_message_needs_no_card(cfg):
    rig = await make_cu_rig(cfg, _OFF_FENCE + " My email is ana@example.com")
    cu = rig.computer()
    await step(cu, "look")
    await step(cu, "click", target={"text": "Note"}, expect="focused")
    done = await step(cu, "type", text="write to ana@example.com", source={"from": "message"}, expect="saved")
    assert done.parked is None and rig.desk._screen_page.pasted_lengths == (len("write to ana@example.com"),)


async def test_password_box_suggests_take_control(rig):
    cu = rig.computer()
    await step(cu, "look")
    refused = await step(cu, "click", target={"text": "Password"}, expect="focused")
    assert refused.text == ACT_TEXTS.password and "take over" in refused.text
    assert rig.desk.inputs == ()


async def test_input_is_refused_while_you_hold_control(rig):
    runner = rig.tool_runner()
    assert SCREENSHOT_SHOWN in await run_step(runner, "look")
    rig.control.take(rig.bot.id)
    assert await run_step(runner, "click", target={"text": "Jobs"}, expect="jobs") == CONTROL_HELD_TEXT
    assert rig.desk.inputs == ()
    rig.control.give_back(rig.bot.id)
    assert await run_step(runner, "click", target={"text": "Jobs"}, expect="jobs") == TAKEN_TEXT
    assert rig.desk.inputs == ()


async def test_pointer_event_has_no_text(rig):
    cu = rig.computer()
    await step(cu, "look")
    await step(cu, "click", target={"text": "Note"}, expect="focused")
    await step(cu, "type", text="blue wool socks size 42", source={"from": "message"}, expect="saved")
    pointers = rig.events.pointers()
    assert [p["kind"] for p in pointers] == ["click", "type"]
    for frame in pointers:
        assert set(frame) == {"type", "bot_id", "x", "y", "kind"}
        assert "wool" not in str(frame)


async def test_a_tainted_run_still_parks_committing_clicks(rig):
    cu = rig.computer()
    await step(cu, "look")
    asked = await step(cu, "click", ctx(mode="auto_edit", tainted=True), target={"text": "Buy now"}, expect="paid")
    assert asked.parked is not None and asked.parked.floor == "commit_click" and asked.parked.tainted_basis
    assert rig.page.state_name == "shop" and rig.desk.inputs == ()


async def test_a_routine_run_gets_blocked_not_a_card(rig):
    runner = rig.tool_runner(cards=False)
    await run_step(runner, "look")
    text = await run_step(runner, "click", target={"text": "Buy now"}, expect="paid")
    assert text == NEEDS_YOUR_OK_TEXT and runner.parked is None and rig.desk.inputs == ()


async def test_a_card_parks_the_tool_runner(rig):
    runner = rig.tool_runner()
    await run_step(runner, "look")
    assert await run_step(runner, "click", target={"text": "Buy now"}, expect="paid") == PARKED_TEXT
    assert runner.parked is not None and runner.parked.tool == "click" and runner.tainted


async def test_one_loop_per_computer_at_a_time(rig):
    first, second = rig.computer("run-1"), rig.computer("run-2")
    await step(first, "look")
    assert (await step(second, "look")).text == BUSY_TEXT
    await first.close()
    assert rig.leases.holder(rig.bot.id) is None and not rig.desk.guards_armed
    assert (await step(second, "look")).looked


async def test_the_guards_hold_this_chats_fence(rig):
    cu = rig.computer()
    await step(cu, "look")
    assert rig.desk.guards_armed and rig.desk.guard_fences[-1].allows("shop.example")
    assert not rig.desk.guard_fences[-1].allows("partner.example")


async def test_scroll_needs_a_look_before_the_next_click(rig):
    cu = rig.computer()
    await step(cu, "look")
    scrolled = await step(cu, "scroll", direction="down", amount=2)
    assert "Scrolled down" in scrolled.text and rig.events.pointers()[-1]["kind"] == "scroll"
    assert (await step(cu, "click", target={"text": "Jobs"}, expect="jobs")).text == LOOK_FIRST_TEXT


async def test_bad_arguments_are_refused_in_plain_words(rig):
    cu = rig.computer()
    await step(cu, "look")
    refused = await step(cu, "press_key", key="Ctrl+W", expect="closed")
    assert refused.text.startswith("Refused:") and rig.desk.inputs == ()


async def test_mac_brave_bots_have_no_screen_tools(rig):
    runner = rig.tool_runner()
    runner_without = type(runner)(
        user_id=rig.user_id, bot_id=rig.bot.id, desk=rig.desk, gate=rig.gate, activity=runner._activity,
        events=runner._events, allowed=frozenset({"get_time"}), thread_id=rig.thread_id,
    )
    assert "Refused" in await run_step(runner_without, "look")


async def test_a_point_outside_the_page_is_refused(rig):
    cu = rig.computer()
    await step(cu, "look")
    refused = await step(cu, "click", x=10, y=780, expect="something")
    assert "outside the page" in refused.text and rig.desk.inputs == ()


def test_box_center_is_the_click_point():
    assert Box(10, 10, 20, 20).center() == (20, 20)


async def test_enter_in_a_lone_box_asks_first(rig):
    cu = rig.computer()
    await step(cu, "look")
    await step(cu, "click", target={"text": "Note"}, expect="focused")
    await step(cu, "look")
    asked = await step(cu, "press_key", key="Enter", expect="saved")
    assert asked.parked is not None and asked.parked.title == "Press Enter"
    assert {row.label for row in asked.parked.rows} >= {"Key", "On", "What it does"}


async def test_escape_on_a_box_just_happens(rig):
    cu = rig.computer()
    await step(cu, "look")
    await step(cu, "click", target={"text": "Note"}, expect="focused")
    await step(cu, "look")
    done = await step(cu, "press_key", key="Escape", expect="nothing changes")
    assert done.parked is None and "Pressed Escape" in rig.lines
    assert rig.events.pointers()[-1]["kind"] == "key"


async def test_what_the_guards_saw_reaches_the_next_look(rig):
    cu = rig.computer()
    await step(cu, "look")
    rig.desk.fake_guards.blocked = "evil.example"
    rig.desk.fake_guards.closed = ("https://popup.example/win",)
    rig.desk.fake_guards.chooser = True
    seen = (await step(cu, "look")).text
    assert "evil.example" in seen and "popup.example" in seen and "file" in seen


async def test_wait_ready_says_ready(rig):
    cu = rig.computer()
    assert (await step(cu, "wait_ready", timeout_s=1)).text == "Page: ready."
    assert "Waiting for the page" in rig.lines


async def test_a_click_on_a_sleeping_computer_wakes_it_but_clicks_nothing_before_a_look(rig):
    cu = rig.computer()
    await step(cu, "look")
    await rig.desk.stop_browser()
    done = await step(cu, "click", target={"text": "Jobs"}, expect="jobs")
    assert done.text == WOKE_LOOK_FIRST_TEXT and rig.page.state_name == "shop"
    assert (await rig.desk.status()).browser == "running"


async def test_typing_runs_with_no_card_and_needs_no_quote(cfg):
    """Owner, 2026-11-03: typing never asks, so a quote (yours or not) changes nothing for it."""
    rig = await make_cu_rig(cfg, "please put a note saying blue socks are fine")   # no site named: not trusted
    cu = rig.computer()
    await step(cu, "look")
    await step(cu, "click", target={"text": "Note"}, expect="the note box is focused")
    done = await step(cu, "type", text="blue socks fine", source={"from": "message"}, expect="note saved",
                      owner_words="put a note saying blue socks fine")
    assert done.parked is None and rig.desk._screen_page.pasted_lengths == (15,)
    assert "Typed into 'Note' (15 characters)" in rig.lines


async def test_your_words_never_buy(cfg):
    rig = await make_cu_rig(cfg, "On shop.example buy now the wool socks please")
    cu = rig.computer()
    await step(cu, "look")
    asked = await step(cu, "click", target={"text": "Buy now"}, expect="paid",
                       owner_words="buy now the wool socks please")
    assert asked.parked is not None and asked.parked.floor == "commit_click" and rig.desk.inputs == ()


async def test_a_look_at_a_list_popup_address_points_to_the_plain_page(rig):
    """Owner, 2026-11-01: Gigs looked at a tab still showing Upwork's 500 for the search popup address and called it
    an outage; Roost's own line (outside the page wrapper) names the job's plain page to open instead."""
    popup = "https://www.upwork.com/nx/search/jobs/details/~0221"

    async def url() -> str:
        return popup
    rig.page.url = url
    seen = (await step(cu := rig.computer(), "look")).text
    assert seen.split("</untrusted_page>", 1)[1].count("open_page https://www.upwork.com/jobs/~0221") == 1
    del rig.page.url                        # back to the fake shop's own address: no line
    assert "open_page" not in (await step(cu, "look")).text.split("</untrusted_page>", 1)[1]


async def test_a_look_at_an_upwork_job_page_names_the_apply_form(rig):
    """Owner, 2026-11-01: Grok's Upwork bot opened the apply form by its address; Roost's own line names it."""
    async def url() -> str:
        return "https://www.upwork.com/jobs/~0221"
    rig.page.url = url
    seen = (await step(rig.computer(), "look")).text.split("</untrusted_page>", 1)[1]
    assert "open_page https://www.upwork.com/nx/proposals/job/~0221/apply/" in seen
