"""Unit tests for ``roost.desk.fake.FakeDesk`` — the in-memory ``Desk``
stand-in every test and ``ROOST_DESK=fake`` run uses. The gateway-route
side of this (the HTTP 503 mapping) is covered by
``tests/test_desk_api.py``; this file is the facade's own direct
contract: state transitions, call recording, and ``force_unavailable``
on every method.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from roost.desk import DeskStatus, DeskUnavailable, ExecResult, PageText
from roost.desk.fake import FakeDesk
from roost.desk.fake_pages import CHALLENGE, CLEARED, FAKE_PAGES, LOGIN_WALL, SIGNED_IN
from roost.desk.stuck import detect_block
from roost.desk.url_policy import UrlBlocked, check_url

_BOT_ID = "bot-1"
_SHOP = "https://shop.example/"


def _page(title: str, *, status: int | None = 200) -> PageText:
    return PageText(url=_SHOP, title=title, text=f"{title} text", truncated=False, status=status)


async def test_initial_status_is_stopped_and_absent():
    desk = FakeDesk(_BOT_ID)
    assert await desk.status() == DeskStatus(browser="stopped", workspace="absent")


async def test_start_then_stop_browser_round_trip():
    desk = FakeDesk(_BOT_ID)
    assert (await desk.start_browser()).browser == "running"
    assert (await desk.stop_browser()).browser == "stopped"


async def test_open_page_records_the_checked_url_and_returns_page_text():
    desk = FakeDesk(_BOT_ID)
    result = await desk.open_page("https://example.com/")
    assert result.url == "https://example.com/"
    assert "example.com" in result.text
    assert desk.open_page_calls == ["https://example.com/"]


async def test_open_page_enforces_the_url_policy():
    desk = FakeDesk(_BOT_ID)
    with pytest.raises(UrlBlocked):
        await desk.open_page("http://127.0.0.1")
    assert desk.open_page_calls == []


async def test_read_page_without_a_prior_open_page_uses_about_blank():
    desk = FakeDesk(_BOT_ID)
    result = await desk.read_page()
    assert result.url == "about:blank"


async def test_read_page_after_open_page_reflects_the_last_opened_url():
    desk = FakeDesk(_BOT_ID)
    await desk.open_page("https://example.com/")
    result = await desk.read_page()
    assert result.url == "https://example.com/"


async def test_exec_records_the_shell_argv_and_fixed_timeout():
    desk = FakeDesk(_BOT_ID)
    result = await desk.exec("echo hi")
    assert result == ExecResult(exit_code=0, stdout="", stderr="", timed_out=False, truncated=False)
    assert desk.exec_calls == [(["/bin/sh", "-c", "echo hi"], 120)]


async def test_exec_marks_the_workspace_running_once():
    desk = FakeDesk(_BOT_ID)
    assert (await desk.status()).workspace == "absent"
    await desk.exec("true")
    assert (await desk.status()).workspace == "running"


async def test_retire_resets_browser_and_workspace_and_marks_retired():
    desk = FakeDesk(_BOT_ID)
    await desk.start_browser()
    await desk.exec("true")

    await desk.retire()

    assert desk.retired is True
    assert await desk.status() == DeskStatus(browser="stopped", workspace="absent")


@pytest.mark.parametrize(
    "call",
    [
        lambda d: d.status(),
        lambda d: d.start_browser(),
        lambda d: d.stop_browser(),
        lambda d: d.open_page("https://example.com/"),
        lambda d: d.read_page(),
        lambda d: d.exec("echo hi"),
        lambda d: d.retire(),
    ],
)
async def test_every_method_raises_desk_unavailable_when_forced(call):
    desk = FakeDesk(_BOT_ID, force_unavailable=True)
    with pytest.raises(DeskUnavailable):
        await call(desk)


def test_fake_jpeg_is_a_real_small_jpeg():
    from roost.desk.fake import FAKE_JPEG
    assert len(FAKE_JPEG) == 631 and FAKE_JPEG.startswith(b"\xff\xd8") and FAKE_JPEG.endswith(b"\xff\xd9")


async def test_screenshot_of_a_running_browser_is_the_fake_jpeg():
    from roost.desk.fake import FAKE_JPEG
    desk = FakeDesk(_BOT_ID)
    await desk.start_browser()
    assert await desk.screenshot() == FAKE_JPEG


async def test_screenshot_of_a_stopped_browser_is_asleep():
    from roost.desk import DeskAsleep
    desk = FakeDesk(_BOT_ID)
    with pytest.raises(DeskAsleep):
        await desk.screenshot()


# -- scripted pages (stuck flow, design R11) ----------------------------


async def test_a_served_url_returns_its_pages_in_order_and_the_last_one_repeats():
    desk = FakeDesk(_BOT_ID)
    desk.serve(_SHOP, _page("first", status=403), _page("second"))
    titles = [(await desk.open_page(_SHOP)).title for _ in range(3)]
    assert titles == ["first", "second", "second"]
    assert desk.open_page_calls == [_SHOP, _SHOP, _SHOP]


async def test_open_page_keeps_the_served_status_and_read_page_drops_it():
    desk = FakeDesk(_BOT_ID)
    desk.serve(_SHOP, _page("wall", status=403), _page("inside", status=200))
    opened = await desk.open_page(_SHOP)
    read = await desk.read_page()
    assert (opened.title, opened.status) == ("wall", 403)
    assert (read.title, read.status) == ("inside", None)


async def test_an_unserved_url_still_gets_the_plain_fake_page():
    desk = FakeDesk(_BOT_ID)
    desk.serve(_SHOP, _page("served"))
    opened = await desk.open_page("https://example.com/")
    assert opened == PageText(
        url="https://example.com/", title="Fake Page", text="Fake content for https://example.com/", truncated=False
    )
    read = await desk.read_page()
    assert read == PageText(url="https://example.com/", title="Fake Page", text="Fake content", truncated=False)


async def test_serving_a_url_again_starts_its_pages_over():
    desk = FakeDesk(_BOT_ID)
    desk.serve(_SHOP, _page("one"), _page("two"))
    await desk.open_page(_SHOP)
    desk.serve(_SHOP, _page("again"), _page("after"))
    assert (await desk.open_page(_SHOP)).title == "again"


def test_serve_needs_at_least_one_page():
    with pytest.raises(ValueError, match="at least one page"):
        FakeDesk(_BOT_ID).serve(_SHOP)


def test_serving_an_address_the_bot_may_not_open_is_refused():
    with pytest.raises(UrlBlocked):
        FakeDesk(_BOT_ID).serve("http://127.0.0.1/", _page("never"))


async def test_a_served_page_is_found_without_its_trailing_slash():
    desk = FakeDesk(_BOT_ID)
    desk.serve(_SHOP, _page("served"))
    assert (await desk.open_page("https://shop.example")).title == "served"


async def test_the_default_pages_include_the_login_wall_then_the_signed_in_page():
    desk = FakeDesk(_BOT_ID)
    wall = await desk.open_page("https://login.example/")
    assert wall == LOGIN_WALL
    assert (wall.password_field, wall.status) == (True, 200)
    assert await desk.read_page() == replace(SIGNED_IN, status=None)
    assert await desk.read_page() == replace(SIGNED_IN, status=None)   # the last page repeats


async def test_the_default_challenge_stays_for_two_loads_then_clears():
    desk = FakeDesk(_BOT_ID)
    first = await desk.open_page("https://challenge.example/")
    again = await desk.open_page("https://challenge.example/")   # rung 1 repeats the same call
    after = await desk.read_page()                                 # the continue run reads the page again
    assert (first, again) == (CHALLENGE, CHALLENGE)
    assert after == replace(CLEARED, status=None)


async def test_each_desk_keeps_its_own_place_in_the_default_pages():
    one, two = FakeDesk("bot-1"), FakeDesk("bot-2")
    await one.open_page("https://login.example/")
    assert await two.open_page("https://login.example/") == LOGIN_WALL


async def test_an_empty_pages_table_serves_nothing():
    desk = FakeDesk(_BOT_ID, pages={})
    assert (await desk.open_page("https://login.example/")).title == "Fake Page"


def test_the_fake_page_addresses_pass_the_url_policy():
    """check_url refuses every local address, so the fake pages live on
    reserved .example hosts that it lets through unchanged."""
    assert [check_url(url) for url in FAKE_PAGES] == list(FAKE_PAGES)
    assert set(FAKE_PAGES) == {"https://login.example/", "https://challenge.example/"}


def test_the_fake_pages_read_as_the_blocks_they_stand_for():
    """The E2E (design R11) relies on these: the wall is a sign-in block,
    the check is a challenge, and the pages behind them are clear."""
    reasons = [getattr(detect_block(page), "reason", None) for page in (LOGIN_WALL, CHALLENGE, SIGNED_IN, CLEARED)]
    assert reasons == ["login", "challenge", None, None]


def test_the_fake_pages_table_cannot_be_changed():
    with pytest.raises(TypeError):
        FAKE_PAGES["https://login.example/"] = ()  # type: ignore[index]
