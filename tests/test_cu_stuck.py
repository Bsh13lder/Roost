"""C3 Task 12: the ladder (R4) and the budget end in a Stuck card with a reason and the next step in your own chat,
and in a loud ``Blocked:`` result anywhere else; a look that meets a sign-in page hands off like ``read_page``."""

from __future__ import annotations

from dataclasses import replace

import pytest

from roost.computer_use.runner import COVERED_TEXT
from roost.computer_use.session import BUDGET_TEXT
from roost.config import load_config
from roost.constants import CU_MAX_ACTS_PER_RUN, CU_TRIES_PER_TARGET
from roost.db.connection import init_db
from roost.desk.fake_cu import FakeScreenState, fake_target, script
from roost.talk.instructions import SIGN_IN_PAGE_NOTE

from cu_run_helpers import make_cu_rig, run_step, step


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def rig(cfg):
    return await make_cu_rig(cfg)


async def _miss_twice(runner) -> str:
    await run_step(runner, "look")
    first = await run_step(runner, "click", target={"text": "Checkout"}, expect="the cart shows")
    assert "Look again" in first and runner.block is None and runner.wall is None
    # Owner, 2026-10-29: a name the page doesn't have, tried again, got Gela stuck on WhatsApp; aim another way.
    assert "number" in first and "point" in first
    for _ in range(CU_TRIES_PER_TARGET - 2):          # owner, 2026-11-03: four tries in all
        await run_step(runner, "look")
        again = await run_step(runner, "click", target={"text": "Checkout"}, expect="the cart shows")
        assert runner.block is None and runner.wall is None and "Stuck" not in again
    await run_step(runner, "look")
    return await run_step(runner, "click", target={"text": "Checkout"}, expect="the cart shows")


async def test_second_miss_opens_a_stuck_card_with_next_step(rig):
    runner = rig.tool_runner(cards=True)
    text = await _miss_twice(runner)
    assert runner.block is not None and runner.block.reason == "asked"
    assert runner.block.host == "shop.example" and runner.block.url == "https://shop.example/"
    assert "Next:" in runner.block.note and "shop.example" in runner.block.note
    assert "'Checkout'" in runner.block.note        # the card names what it looked for, not "that"
    assert "Stuck" in text and rig.desk.inputs == ()


async def test_a_second_miss_in_a_routine_is_a_blocked_result(rig):
    runner = rig.tool_runner(cards=False)
    text = await _miss_twice(runner)
    assert runner.block is None and runner.wall is not None
    assert text.startswith("Blocked:") and "Next:" in text


async def test_a_miss_needs_a_fresh_look_before_trying_again(rig):
    cu = rig.computer()
    await step(cu, "look")
    await step(cu, "click", target={"text": "Checkout"}, expect="cart")
    assert (await step(cu, "click", target={"text": "Checkout"}, expect="cart")).text.startswith("Look first")


async def test_a_covered_target_counts_toward_the_two_tries(rig):
    covered = (fake_target("button", "Jobs", 450, 100, tag="button"),
               fake_target("button", "No thanks", 600, 300, tag="button", in_dialog="Newsletter"))
    rig.desk.serve_screen(script([("pop", FakeScreenState(url="https://shop.example/", title="Shop",
                                                           targets=covered, dialog="Newsletter"))]))
    cu = rig.computer()
    await step(cu, "look")
    first = await step(cu, "click", target={"text": "Jobs"}, expect="jobs")
    assert first.text.startswith(COVERED_TEXT.split("{", 1)[0]) and first.block is None
    assert "'Jobs'" in first.text and "'No thanks'" in first.text and "Escape" in first.text   # its own closer
    for _ in range(CU_TRIES_PER_TARGET - 2):
        await step(cu, "look")
        assert (await step(cu, "click", target={"text": "Jobs"}, expect="jobs")).block is None
    await step(cu, "look")
    second = await step(cu, "click", target={"text": "Jobs"}, expect="jobs")
    assert second.block is not None and "Next:" in second.block.note
    assert rig.desk.inputs == ()


async def test_a_spent_budget_goes_stuck_with_the_budget_note(rig):
    runner = rig.tool_runner(cards=True)
    await run_step(runner, "look")
    computer = runner._computer
    computer.state = replace(computer.state, acts=CU_MAX_ACTS_PER_RUN)
    text = await run_step(runner, "click", target={"text": "Jobs"}, expect="jobs")
    assert BUDGET_TEXT in text and runner.block is not None
    assert "step budget on shop.example" in runner.block.note and "Next:" in runner.block.note


async def test_a_look_at_a_sign_in_page_carries_a_note_and_no_card(rig):
    """Owner, 2026-11-03: the bot signs in itself; only ask_secret_field or request_sign_in opens the card."""
    rig.desk.serve_screen(script([("login", FakeScreenState(
        url="https://shop.example/login", title="Sign in", text="Sign in to continue", password_field=True,
        targets=(fake_target("field", "Password", 100, 100, tag="input", input_type="password",
                             secret_field=True),)))]))
    runner = rig.tool_runner(cards=True)
    text = await run_step(runner, "look")
    assert runner.block is None and SIGN_IN_PAGE_NOTE in text and runner.tainted
