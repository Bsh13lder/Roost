"""web_search (owner, 2026-10-23, A3): one fixed search host read through the bot's own browser, up to 10 results
escaped as untrusted, the run tainted like any page, and each result's host added to the link scope so open_page
may open it."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from roost.config import load_config
from roost.constants import WEB_SEARCH_HOST, WEB_SEARCH_MAX_RESULTS, WEB_SEARCH_QUERY_MAX, WEB_SEARCH_URL
from roost.db.connection import init_db
from roost.desk import DeskUnavailable, PageText
from roost.desk.browser import DeskBrowserPage
from roost.desk.client import KeeperDesk
from roost.desk.fake import FakeDesk
from roost.gateway.auth import register_user
from roost.helpers.desk_lock import LockedDesk
from roost.llm.types import ToolCallRequested, TurnDone
from roost.research.fake_results import FAKE_SEARCH_HTML
from roost.research.results import SearchResult, parse_results
from roost.research.search import (
    BAD_QUERY_TEXT, NO_RESULTS_TEXT, result_scope, search_query, search_url, wrap_results,
)
from roost.talk.gate import LINK_REFUSAL_TEXT
from roost.talk.link_scope import LinkScope
from roost.talk.tool_catalog import CATALOG
from roost.talk.tools import EVERY_BOT_TOOLS
from team_helpers import make_bot, make_rig, say, send, team_model, wait_idle

PASSWORD = "pw-123456"


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


# --- parsing the results page ------------------------------------------------------------------------------------

def test_the_results_are_decoded_capped_and_ads_and_odd_links_left_out():
    results = parse_results(FAKE_SEARCH_HTML)
    assert len(results) == WEB_SEARCH_MAX_RESULTS
    first = results[0]
    assert first == SearchResult(title="The best kettles of 2026", url="https://kettles.example/best?x=1&y=2",
                                 snippet="We tested 20 kettles & picked three.")
    assert results[1].url == "https://tea.example/" and results[1].title.startswith("<script>")
    assert all("duckduckgo.com" not in r.url and r.url.startswith("https://") for r in results)


def test_an_empty_or_strange_page_has_no_results():
    assert parse_results("") == ()
    assert parse_results("<html><body><p>No results.</p></body></html>") == ()
    assert parse_results('<a class="result__a" href="//duckduckgo.com/l/?uddg=">x</a>') == ()


def test_a_direct_link_is_kept_and_a_long_title_is_cut():
    html = f'<div class="result"><a class="result__a" href="https://a.example/">{"T" * 500}</a></div>'
    [result] = parse_results(html)
    assert result.url == "https://a.example/" and len(result.title) <= 201 and result.snippet == ""


# --- the query, the wrapper and the scope ------------------------------------------------------------------------

def test_the_query_is_checked_and_encoded_on_the_fixed_host():
    assert search_query({"query": "  best  kettles "}) == "best kettles"
    assert search_query({"query": ""}) is None and search_query({}) is None
    assert search_query({"query": "x" * (WEB_SEARCH_QUERY_MAX + 1)}) is None
    url = search_url("kettles & tea")
    assert url.startswith(WEB_SEARCH_URL) and url.endswith("?q=kettles+%26+tea")


def test_the_results_are_escaped_as_untrusted():
    text = wrap_results("kettles", parse_results(FAKE_SEARCH_HTML))
    assert text.startswith(f'<untrusted_page url="{WEB_SEARCH_URL}')
    assert "<script>" not in text and "&lt;script&gt;" in text
    assert "1. The best kettles of 2026" in text and "https://kettles.example/best?x=1&amp;y=2" in text
    assert wrap_results("kettles", ()).endswith(NO_RESULTS_TEXT + "</untrusted_page>")


def test_each_result_host_joins_the_scope():
    scope = LinkScope().merge(result_scope(parse_results(FAKE_SEARCH_HTML)))
    assert scope.allows("https://kettles.example/best?x=1&y=2")
    assert scope.allows("https://tea.example/another/page")
    assert not scope.allows("https://evil.example/")


# --- the desks --------------------------------------------------------------------------------------------------

async def test_the_fake_desk_serves_the_fixture_for_the_search_host_only():
    desk = FakeDesk("b1")
    found = await desk.search_page(search_url("kettles"))
    assert found.html == FAKE_SEARCH_HTML and found.page.url.startswith(WEB_SEARCH_URL)
    other = await desk.search_page("https://elsewhere.example/")
    assert other.html == ""


async def test_the_locked_desk_takes_its_turn_for_a_search():
    locked = LockedDesk(FakeDesk("b1"))
    assert (await locked.search_page(search_url("tea"))).html == FAKE_SEARCH_HTML


class _HtmlPage:
    def __init__(self) -> None:
        self.urls: list[str] = []

    async def open_and_html(self, url: str) -> tuple[PageText, str]:
        self.urls.append(url)
        return PageText(url=url, title="r", text="r", truncated=False), "<html></html>"

    async def close(self) -> None: ...


async def test_the_keeper_desk_opens_and_reads_the_html():
    page = _HtmlPage()

    async def connect(relay_url: str, token: str) -> _HtmlPage:
        return page

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"cdp_token": "t", "computer": "running", "workspace": "absent"})

    desk = KeeperDesk(load_config(), "b1", computer="linux", transport=httpx.MockTransport(handler),
                      connect_page=connect)
    found = await desk.search_page(search_url("tea"))
    assert found.html == "<html></html>" and page.urls == [search_url("tea")]


class _DomCdp:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def send(self, method: str, params: dict[str, Any] | None = None, session_id: str | None = None) -> dict:
        self.calls.append(method)
        if method == "DOM.getDocument":
            return {"result": {"root": {"nodeId": 7}}}
        return {"result": {"outerHTML": "<html>" + "x" * 10 + "</html>"}}


async def test_the_browser_page_reads_the_documents_html_by_fixed_cdp():
    page = object.__new__(DeskBrowserPage)
    page._client = _DomCdp()

    async def session() -> str:
        return "S1"

    async def opened(url: str) -> PageText:
        return PageText(url=url, title="t", text="t", truncated=False)

    page._ensure_session = session
    page.open_page = opened
    found, html = await page.open_and_html(WEB_SEARCH_URL)
    assert html.startswith("<html>") and page._client.calls == ["DOM.getDocument", "DOM.getOuterHTML"]


# --- the tool in a run -------------------------------------------------------------------------------------------

def _call(call_id: str, name: str, **arguments) -> ToolCallRequested:
    return ToolCallRequested(id=call_id, name=name, arguments=arguments)


def test_web_search_is_every_bots_read_tool():
    assert CATALOG["web_search"].kind == "read" and "web_search" in EVERY_BOT_TOOLS


async def _run(cfg, steps, *, unavailable: bool = False):
    user = (await register_user(cfg, "alice", PASSWORD)).id
    bot = await make_bot(cfg, user, "Helper")
    model = team_model({"Helper": steps})
    rig = make_rig(cfg, model)
    desk = rig.desks.for_bot(bot.id, bot.computer)
    desk.force_unavailable = unavailable
    thread = await rig.talk.create_thread(user, bot.id)
    await send(rig, user, bot.id, thread.id, "Find me a good kettle and add a task for it.")
    await wait_idle(rig.runner, timeout=8)
    return desk, model, await rig.talk.list_messages(user, thread.id)


def _results_of(model) -> list[str]:
    """Every tool result the model was shown, oldest first."""
    seen = [turn.text for request in model.requests for turn in request.turns if turn.role == "tool"]
    return list(dict.fromkeys(seen))


async def test_a_search_result_may_be_opened_in_a_guarded_run_and_other_links_may_not(cfg):
    desk, model, messages = await _run(cfg, [
        [_call("l", "list_tasks"), TurnDone("tool_use")],
        [_call("s", "web_search", query="best kettle"), TurnDone("tool_use")],
        [_call("o", "open_page", url="https://tea.example/green"), TurnDone("tool_use")],
        [_call("e", "open_page", url="https://evil.example/"), TurnDone("tool_use")],
        say("Done.")])
    assert desk.open_page_calls[0].startswith(WEB_SEARCH_URL)
    assert "https://tea.example/green" in desk.open_page_calls
    assert "https://evil.example/" not in desk.open_page_calls
    assert any(LINK_REFUSAL_TEXT in text for text in _results_of(model))
    assert [m for m in messages if m.role == "bot" and m.kind == "text"][-1].tainted


async def test_a_bad_query_or_an_unreachable_computer_is_said_plainly(cfg):
    desk, model, _ = await _run(cfg, [
        [_call("s", "web_search", query=""), TurnDone("tool_use")],
        [_call("t", "web_search", query="kettles"), TurnDone("tool_use")],
        say("Done.")], unavailable=True)
    texts = _results_of(model)
    assert any(BAD_QUERY_TEXT in text for text in texts)
    assert any("computer" in text.lower() and "kettles" not in text for text in texts)
    assert WEB_SEARCH_HOST not in "".join(desk.open_page_calls)
