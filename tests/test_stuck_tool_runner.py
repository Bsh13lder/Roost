"""ToolRunner and the stuck ladder (stuck flow, Task 4): rung 1's wait and
repeat, blocks, the refused-once rule and ask_for_help. Pages come from
FakeDesk.serve (Task 2). The 8-second wait is patched on the name
tool_runner imported (roost.talk.tool_runner.STUCK_CHALLENGE_WAIT_SECONDS)."""

from __future__ import annotations

import asyncio
import time

import pytest

import roost.talk.tool_runner as tool_runner_module
from roost.bots.status import ActivityBoard
from roost.config import load_config
from roost.constants import STUCK_REASON_MAX_CHARS
from roost.db.connection import init_db
from roost.desk import PageText
from roost.desk.control import ControlLock
from roost.desk.fake import FakeDesk
from roost.desk.stuck import Block
from roost.events.hub import EventHub
from roost.gateway.auth import register_user
from roost.llm.types import ToolCallRequested
from roost.talk.gate import Gate
from roost.talk.instructions import (
    ASK_ONLY_IN_CHAT_TEXT, ASKED_FOR_HELP_TEXT, BAD_HELP_ARGS_TEXT, STUCK_NOT_PERFORMED_TEXT,
    blocked_result_text, refused_once_text, stuck_result_text,
)
from roost.talk.stuck_check import check_page
from roost.talk.tool_catalog import CATALOG
from roost.talk.tool_runner import ToolRunner, wrap_page
from team_helpers import make_bot, until

_URL = "https://shop.example/item"
_HOST = "shop.example"
_OTHER_URL = "https://other.example/item"
_WAITING = f"waiting for {_HOST} to let me in"
_UNAVAILABLE = "Your computer is unavailable right now."


def _page(title: str, text: str, *, url: str = _URL, status: int | None = 200,
          password_field: bool = False) -> PageText:
    return PageText(url=url, title=title, text=text, truncated=False, status=status,
                    password_field=password_field)


_ARTICLE = _page("Blue kettle", "The blue kettle costs 40 euros and ships in two days.")
_CHALLENGE = _page("Just a moment...", "Checking your browser before accessing shop.example.", status=403)
_LOGIN = _page("Sign in", "Sign in to continue. Email. Forgot your password?", password_field=True)
_CODE = _page("Two-step verification",
              "Enter the verification code we sent to your phone. No code? https://help.example/2fa")
_REFUSED = _page("Forbidden", "Access denied.", status=403)
_OTHER_REFUSED = _page("Too many requests", "Slow down.", url=_OTHER_URL, status=429)


class _Lines(ActivityBoard):
    """Keeps every activity line the runner announced, in order."""

    def __init__(self) -> None:
        super().__init__()
        self.lines: tuple[str, ...] = ()

    def set(self, bot_id: str, text: str | None, *, tainted: bool = False) -> None:
        super().set(bot_id, text, tainted=tainted)
        if text is not None:
            self.lines = (*self.lines, text)


class _TakesControlDesk(FakeDesk):
    """The user presses Take control as the challenge loads, so the hold is there for the whole wait."""

    def __init__(self, bot_id: str, lock: ControlLock) -> None:
        super().__init__(bot_id)
        self._lock = lock

    async def open_page(self, url: str) -> PageText:
        page = await super().open_page(url)
        if page.title == _CHALLENGE.title:
            self._lock.take(self.bot_id)
        return page


class _DownBeforeTheRepeatDesk(FakeDesk):
    """The keeper goes away between the first load and rung 1's repeat."""

    async def open_page(self, url: str) -> PageText:
        page = await super().open_page(url)
        self.force_unavailable = True
        return page


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def ids(cfg):
    user_id = (await register_user(cfg, "alice", "pw-123456")).id
    return user_id, (await make_bot(cfg, user_id, "Scout")).id


@pytest.fixture(autouse=True)
def _short_wait(monkeypatch):
    """Rung 1 waits STUCK_CHALLENGE_WAIT_SECONDS (8 s). tool_runner imports the name, so it is patched there."""
    monkeypatch.setattr(tool_runner_module, "STUCK_CHALLENGE_WAIT_SECONDS", 0.01)


def _runner(cfg, ids, desk: FakeDesk, *, cards: bool, control: ControlLock | None = None) -> ToolRunner:
    user_id, bot_id = ids
    return ToolRunner(
        user_id=user_id, bot_id=bot_id, desk=desk, gate=Gate(cfg), activity=_Lines(), events=EventHub(cfg),
        allowed=frozenset(CATALOG), cards=cards, control=control,
    )


def _served(ids, *pages: PageText, url: str = _URL) -> FakeDesk:
    desk = FakeDesk(ids[1])
    desk.serve(url, *pages)
    return desk


def _open(url: str = _URL, call_id: str = "p") -> ToolCallRequested:
    return ToolCallRequested(id=call_id, name="open_page", arguments={"url": url})


def _read(call_id: str = "r") -> ToolCallRequested:
    return ToolCallRequested(id=call_id, name="read_page", arguments={})


def _ask(reason: object = "a payment check on the card form", call_id: str = "h",
         **extra: object) -> ToolCallRequested:
    return ToolCallRequested(id=call_id, name="ask_for_help", arguments={"reason": reason, **extra})


# ---------------------------------------------------------------------------
# The tool
# ---------------------------------------------------------------------------

def test_ask_for_help_is_a_read_tool_right_after_get_time():
    names = list(CATALOG)
    tool = CATALOG["ask_for_help"]
    assert tool.kind == "read"
    assert names.index("ask_for_help") == names.index("get_time") + 1
    assert tool.spec.input_schema["required"] == ["reason"]
    assert set(tool.spec.input_schema["properties"]) == {"reason", "suggest_main_browser"}
    assert " role" not in tool.spec.description and "control" not in tool.spec.description


# ---------------------------------------------------------------------------
# Rung 1: wait, then repeat the same call once
# ---------------------------------------------------------------------------

async def test_a_page_with_no_block_comes_back_as_usual(cfg, ids):
    desk = _served(ids, _ARTICLE)
    runner = _runner(cfg, ids, desk, cards=True)
    assert await runner.run(_open()) == wrap_page(_ARTICLE)
    assert runner.block is None
    assert (runner.last_host, runner.last_url, runner.tainted) == (_HOST, _URL, True)
    assert desk.open_page_calls == [_URL]
    assert _WAITING not in runner._activity.lines


async def test_a_challenge_that_clears_after_the_wait_returns_the_cleared_page(cfg, ids):
    desk = _served(ids, _CHALLENGE, _ARTICLE)
    runner = _runner(cfg, ids, desk, cards=True)
    assert await runner.run(_open()) == wrap_page(_ARTICLE)
    assert runner.block is None
    assert desk.open_page_calls == [_URL, _URL]          # R4: the same call, repeated once
    assert _WAITING in runner._activity.lines


async def test_rung_one_waits_the_patched_wait_before_the_repeat(cfg, ids, monkeypatch):
    monkeypatch.setattr(tool_runner_module, "STUCK_CHALLENGE_WAIT_SECONDS", 0.2)
    runner = _runner(cfg, ids, _served(ids, _CHALLENGE, _ARTICLE), cards=True)
    started = time.monotonic()
    await runner.run(_open())
    assert time.monotonic() - started >= 0.2


async def test_a_challenge_on_read_page_repeats_read_page(cfg, ids):
    desk = _served(ids, _ARTICLE, _CHALLENGE, _ARTICLE)
    runner = _runner(cfg, ids, desk, cards=True)
    await runner.run(_open())
    assert await runner.run(_read()) == wrap_page(_ARTICLE)
    assert runner.block is None
    assert desk.open_page_calls == [_URL]                 # the repeat was read_page again, not open_page


async def test_a_challenge_that_stays_sets_the_block_in_your_own_chat(cfg, ids):
    desk = _served(ids, _CHALLENGE)
    runner = _runner(cfg, ids, desk, cards=True)
    text = await runner.run(_open())
    assert runner.block == Block(reason="challenge", url=_URL, host=_HOST)
    assert text == stuck_result_text(runner.block)
    assert "Checking your browser" not in text            # the wall's own text never reaches the model
    assert desk.open_page_calls == [_URL, _URL]
    assert (runner.last_host, runner.last_url, runner.tainted) == (_HOST, _URL, True)
    assert runner.link_scope.allows(_URL)


async def test_a_challenge_that_stays_in_any_other_run_is_a_loud_result_and_no_block(cfg, ids):
    desk = _served(ids, _CHALLENGE)
    runner = _runner(cfg, ids, desk, cards=False)
    text = await runner.run(_open())
    assert text == blocked_result_text(Block(reason="challenge", url=_URL, host=_HOST))
    assert text.startswith("Blocked: ") and runner.block is None
    assert desk.open_page_calls == [_URL, _URL]           # R5: rung 1 runs in every run
    assert runner.tainted is True


@pytest.mark.parametrize(("page", "reason"), [(_CODE, "code")])
async def test_a_code_check_is_a_block_at_once_with_no_wait(cfg, ids, page, reason):
    # A sign-in page is read with a note instead (owner, 2026-11-03; tests/test_signin_page_free.py).
    desk = _served(ids, page, _ARTICLE)
    runner = _runner(cfg, ids, desk, cards=True)
    text = await runner.run(_open())
    assert runner.block == Block(reason=reason, url=_URL, host=_HOST)
    assert text == stuck_result_text(runner.block)
    assert desk.open_page_calls == [_URL]
    assert not any(line.startswith("waiting for") for line in runner._activity.lines)
    assert runner.link_scope.as_tuple() == (_URL,)       # the wall's own links were never shown, so never join


async def test_an_address_the_bot_may_not_open_is_refused_before_any_check(cfg, ids):
    desk = FakeDesk(ids[1])
    runner = _runner(cfg, ids, desk, cards=True)
    assert await runner.run(_open("http://127.0.0.1/")) == "Blocked: that address is not allowed."
    assert runner.block is None and runner.tainted is False and desk.open_page_calls == []


async def test_taking_control_during_the_wait_skips_the_repeat(cfg, ids, monkeypatch):
    """Review Focus 2: the user presses Take control while rung 1 waits. The bot must not
    navigate under the user's hands: no repeat, and the block stands (the card opens)."""
    monkeypatch.setattr(tool_runner_module, "STUCK_CHALLENGE_WAIT_SECONDS", 0.3)
    lock = ControlLock(wait_seconds=0.05)
    desk = _served(ids, _CHALLENGE, _ARTICLE)
    runner = _runner(cfg, ids, desk, cards=True, control=lock)
    call = asyncio.create_task(runner.run(_open()))
    await until(lambda: runner._activity.get(ids[1]) == _WAITING)
    lock.take(ids[1])
    assert await call == stuck_result_text(Block(reason="challenge", url=_URL, host=_HOST))
    assert desk.open_page_calls == [_URL]
    assert runner.block == Block(reason="challenge", url=_URL, host=_HOST)


async def test_take_control_during_the_wait_opens_the_card_at_once(cfg, ids, monkeypatch):
    """I7: Take control cuts rung 1's wait short. With the real 5 s wait the call still returns
    at once, with the block standing and no repeat."""
    monkeypatch.setattr(tool_runner_module, "STUCK_CHALLENGE_WAIT_SECONDS", 5.0)
    lock = ControlLock(wait_seconds=0.05)
    desk = _served(ids, _CHALLENGE, _ARTICLE)
    runner = _runner(cfg, ids, desk, cards=True, control=lock)
    call = asyncio.create_task(runner.run(_open()))
    await until(lambda: runner._activity.get(ids[1]) == _WAITING)
    started = time.monotonic()
    lock.take(ids[1])
    text = await asyncio.wait_for(call, timeout=2.0)
    assert time.monotonic() - started < 1.0
    assert text == stuck_result_text(Block(reason="challenge", url=_URL, host=_HOST))
    assert desk.open_page_calls == [_URL]
    assert runner.block == Block(reason="challenge", url=_URL, host=_HOST)


async def test_control_taken_just_as_the_wait_runs_out_still_skips_the_repeat():
    """The wait ended by its timeout, and the person took control in the instant before the
    check resumed: the repeat is still skipped, so the bot never navigates under their hands."""

    class _TookControlAtTheLastMoment:
        async def wait_taken(self, bot_id: str, timeout: float) -> bool:
            return False

    async def _fetch() -> PageText:
        raise AssertionError("the repeat must not run")

    async def _announce(text: str) -> None:
        return None

    checked = await check_page(_CHALLENGE, _fetch, wait_seconds=0.01, announce=_announce,
                               hands_taken=lambda: True, control=_TookControlAtTheLastMoment(), bot_id="b1")
    assert checked.page is _CHALLENGE
    assert checked.block == Block(reason="challenge", url=_URL, host=_HOST)


async def test_control_taken_as_the_challenge_loads_also_skips_the_repeat(cfg, ids):
    lock = ControlLock(wait_seconds=0.05)
    desk = _TakesControlDesk(ids[1], lock)
    desk.serve(_URL, _CHALLENGE, _ARTICLE)
    runner = _runner(cfg, ids, desk, cards=True, control=lock)
    text = await runner.run(_open())
    assert desk.open_page_calls == [_URL]
    assert runner.block == Block(reason="challenge", url=_URL, host=_HOST)
    assert text == stuck_result_text(runner.block)


async def test_a_computer_that_goes_down_before_the_repeat_says_so(cfg, ids):
    desk = _DownBeforeTheRepeatDesk(ids[1])
    desk.serve(_URL, _CHALLENGE, _ARTICLE)
    runner = _runner(cfg, ids, desk, cards=True)
    assert await runner.run(_open()) == _UNAVAILABLE
    assert runner.block is None and runner.tainted is False


# ---------------------------------------------------------------------------
# Refused: a result the first time per host, a block the second time
# ---------------------------------------------------------------------------

async def test_a_first_refusal_on_a_host_is_a_result_not_a_block(cfg, ids):
    desk = _served(ids, _REFUSED)
    runner = _runner(cfg, ids, desk, cards=True)
    text = await runner.run(_open())
    assert text == refused_once_text(_HOST, 403)
    assert "Access denied" not in text
    assert runner.block is None
    assert desk.open_page_calls == [_URL]                 # a refusal gets no wait and no repeat


async def test_a_second_refusal_on_the_same_host_is_a_block(cfg, ids):
    runner = _runner(cfg, ids, _served(ids, _REFUSED), cards=True)
    await runner.run(_open(call_id="p1"))
    text = await runner.run(_open(call_id="p2"))
    assert runner.block == Block(reason="refused", url=_URL, host=_HOST)
    assert text == stuck_result_text(runner.block)


async def test_refusals_are_counted_per_host(cfg, ids):
    desk = _served(ids, _REFUSED)
    desk.serve(_OTHER_URL, _OTHER_REFUSED)
    runner = _runner(cfg, ids, desk, cards=True)
    assert await runner.run(_open(_URL, "p1")) == refused_once_text(_HOST, 403)
    assert await runner.run(_open(_OTHER_URL, "p2")) == refused_once_text("other.example", 429)
    assert runner.block is None


# ---------------------------------------------------------------------------
# After a block, nothing else in the step runs (R1)
# ---------------------------------------------------------------------------

async def test_after_a_block_every_later_call_is_not_performed(cfg, ids):
    desk = _served(ids, _CODE)
    runner = _runner(cfg, ids, desk, cards=True)
    await runner.run(_open(call_id="p1"))
    assert await runner.run(_open(_OTHER_URL, "p2")) == STUCK_NOT_PERFORMED_TEXT
    assert await runner.run(ToolCallRequested(id="t", name="get_time", arguments={})) == STUCK_NOT_PERFORMED_TEXT
    assert desk.open_page_calls == [_URL]


# ---------------------------------------------------------------------------
# ask_for_help
# ---------------------------------------------------------------------------

async def test_ask_for_help_in_your_own_chat_sets_an_asked_block_on_the_open_page(cfg, ids):
    runner = _runner(cfg, ids, _served(ids, _ARTICLE), cards=True)
    await runner.run(_open())
    text = await runner.run(_ask("The shop wants an ID check before checkout.", suggest_main_browser=True))
    assert text == ASKED_FOR_HELP_TEXT
    assert runner.block == Block(reason="asked", url=_URL, host=_HOST,
                                 note="The shop wants an ID check before checkout.", suggest_main_browser=True)
    assert runner._activity.lines[-1] == "asking you for help"


async def test_ask_for_help_before_any_page_has_no_address(cfg, ids):
    runner = _runner(cfg, ids, FakeDesk(ids[1]), cards=True)
    assert await runner.run(_ask()) == ASKED_FOR_HELP_TEXT
    assert runner.block == Block(reason="asked", url="", host="", note="a payment check on the card form")


async def test_ask_for_help_on_a_blank_tab_has_no_address(cfg, ids):
    """A fresh tab reads as about:blank. That is no web page, so the card names none
    (never "Stuck on about:blank", never a continue line about about:blank)."""
    runner = _runner(cfg, ids, FakeDesk(ids[1]), cards=True)
    await runner.run(_read())
    assert runner.last_url == "about:blank" and runner.block is None
    assert await runner.run(_ask()) == ASKED_FOR_HELP_TEXT
    assert runner.block == Block(reason="asked", url="", host="", note="a payment check on the card form")


async def test_ask_for_help_outside_your_own_chat_is_refused(cfg, ids):
    runner = _runner(cfg, ids, FakeDesk(ids[1]), cards=False)
    assert await runner.run(_ask()) == ASK_ONLY_IN_CHAT_TEXT
    assert runner.block is None


@pytest.mark.parametrize("arguments", [
    {}, {"reason": ""}, {"reason": "   "}, {"reason": "x" * (STUCK_REASON_MAX_CHARS + 1)}, {"reason": 42},
])
async def test_ask_for_help_needs_a_reason_of_1_to_the_cap(cfg, ids, arguments):
    runner = _runner(cfg, ids, FakeDesk(ids[1]), cards=True)
    call = ToolCallRequested(id="h", name="ask_for_help", arguments=arguments)
    assert await runner.run(call) == BAD_HELP_ARGS_TEXT
    assert runner.block is None


async def test_ask_for_help_keeps_the_reason_as_plain_text(cfg, ids):
    runner = _runner(cfg, ids, FakeDesk(ids[1]), cards=True)
    await runner.run(_ask("Ana&#x27;s card &amp; ID"))
    assert runner.block is not None and runner.block.note == "Ana's card & ID"


async def test_asking_twice_in_one_step_is_not_performed_the_second_time(cfg, ids):
    runner = _runner(cfg, ids, FakeDesk(ids[1]), cards=True)
    await runner.run(_ask("first", call_id="h1"))
    assert await runner.run(_ask("second", call_id="h2")) == STUCK_NOT_PERFORMED_TEXT
    assert runner.block is not None and runner.block.note == "first"


# ---------------------------------------------------------------------------
# Owner, 2026-10-31: a server error is loaded again (roost/talk/server_error.py)
# ---------------------------------------------------------------------------

_DOWN = _page("We'll be right back", "Upwork is temporarily unavailable.", status=500)


@pytest.fixture
def _quick_reloads(monkeypatch):
    import roost.talk.server_error as server_error
    monkeypatch.setattr(server_error, "SERVER_ERROR_RELOAD_WAITS_S", (0.01, 0.01))


async def test_open_page_loads_a_server_error_again_and_returns_the_page(cfg, ids, _quick_reloads):
    desk = _served(ids, _DOWN, _ARTICLE)
    runner = _runner(cfg, ids, desk, cards=True)
    assert await runner.run(_open()) == wrap_page(_ARTICLE)
    assert desk.open_page_calls == [_URL, _URL]
    assert "the site answered with an error, loading it again" in runner._activity.lines


async def test_open_page_says_a_site_that_stays_down_is_down(cfg, ids, _quick_reloads):
    desk = _served(ids, _DOWN, _DOWN, _DOWN)
    runner = _runner(cfg, ids, desk, cards=True)
    text = await runner.run(_open())
    assert text.startswith("The page answered with a server error (500) 3 times")
    assert desk.open_page_calls == [_URL, _URL, _URL]


_LIST_POPUP = "https://www.upwork.com/nx/search/jobs/details/~0221"
_JOB_PAGE = "https://www.upwork.com/jobs/~0221"


async def test_open_page_tries_the_jobs_plain_page_when_the_list_popup_errors(cfg, ids, _quick_reloads):
    desk = FakeDesk(ids[1])
    desk.serve(_LIST_POPUP, _page("Upwork", "We'll be right back", url=_LIST_POPUP, status=500))
    job = _page("AI receptionist", "Build an AI phone receptionist for a clinic.", url=_JOB_PAGE)
    desk.serve(_JOB_PAGE, job)
    runner = _runner(cfg, ids, desk, cards=True)
    assert await runner.run(_open(_LIST_POPUP)) == wrap_page(job)
    assert desk.open_page_calls == [_LIST_POPUP, _JOB_PAGE]
