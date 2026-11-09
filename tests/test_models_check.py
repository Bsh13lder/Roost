"""The daily check of Anthropic's public models page: parsing, storing, the bare request, the switch."""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from roost.config import load_config
from roost.constants import MODEL_CHECK_HOST, MODEL_CHECK_MAX_BYTES, MODEL_CHECK_URL
from roost.db.connection import init_db
from roost.gateway.app import create_app
from roost.gateway.auth import register_user
from roost.models_check.fetch import FetchRefused, FilePageFetcher, HttpPageFetcher
from roost.models_check.page import label_for, parse_model_ids
from roost.models_check.scheduler import ModelCheck
from roost.models_check.store import SeenModelStore

FIXTURE = Path(__file__).parent / "fixtures" / "models_page.html"
HTML = FIXTURE.read_text(encoding="utf-8")


class FakeFetcher:
    def __init__(self, page: str | Exception) -> None:
        self.page = page
        self.calls = 0

    async def fetch(self) -> str:
        self.calls += 1
        if isinstance(self.page, Exception):
            raise self.page
        return self.page


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


def test_parse_finds_the_api_ids_and_skips_bedrock_ids():
    ids = parse_model_ids(HTML)
    assert "claude-opus-6" in ids and "claude-sonnet-5-5" in ids and "claude-opus-4-1-20250805" in ids
    assert not any(i.startswith("anthropic.") or "@" in i or i.endswith("v1:0") or "v1" in i for i in ids)
    assert len(ids) == len(set(ids))


def test_labels_read_like_the_registry_ones():
    assert label_for("claude-opus-6") == "Opus 6"
    assert label_for("claude-sonnet-5-5") == "Sonnet 5.5"
    assert label_for("claude-haiku-4-5-20251001") == "Haiku 4.5"


async def test_a_known_id_is_never_new(cfg):
    fetcher = FakeFetcher("<td>claude-sonnet-5-5</td><td>claude-fable-5-1</td><td>claude-haiku-5-5</td>")
    assert await ModelCheck(SeenModelStore(cfg), fetcher).run_once() == ()
    assert await SeenModelStore(cfg).labels() == {}


async def test_run_once_stores_a_new_id_once(cfg):
    store = SeenModelStore(cfg)
    check = ModelCheck(store, FakeFetcher(HTML))
    assert await check.run_once() == ("claude-opus-6",)   # old models on the page are not news
    assert await check.run_once() == ()
    assert await store.labels() == {"claude-opus-6": "Opus 6"}


async def test_a_new_haiku_is_not_offered(cfg):
    await ModelCheck(SeenModelStore(cfg), FakeFetcher("<td>claude-haiku-6</td>")).run_once()
    assert await SeenModelStore(cfg).labels() == {}


async def test_a_failed_or_empty_page_changes_nothing(cfg, caplog):
    store = SeenModelStore(cfg)
    with caplog.at_level(logging.WARNING):
        assert await ModelCheck(store, FakeFetcher(RuntimeError("secret detail 123"))).run_once() == ()
        assert await ModelCheck(store, FakeFetcher("<html>nothing here</html>")).run_once() == ()
    assert await store.labels() == {}
    assert "RuntimeError" in caplog.text and "secret detail" not in caplog.text


def _fetcher(handler) -> HttpPageFetcher:
    return HttpPageFetcher(transport=httpx.MockTransport(handler))


async def test_the_check_sends_a_bare_request_to_one_host():
    seen: list[httpx.Request] = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, text=HTML)

    assert "claude-opus-6" in await _fetcher(handler).fetch()
    [request] = seen
    assert (request.method, str(request.url), request.url.host) == ("GET", MODEL_CHECK_URL, MODEL_CHECK_HOST)
    assert not {"cookie", "authorization", "x-api-key"} & {k.lower() for k in request.headers}
    assert request.content == b""


async def test_a_cross_host_redirect_is_not_followed_and_an_oversized_body_is_refused():
    seen: list[str] = []

    def elsewhere(request):
        seen.append(request.url.host)
        return httpx.Response(302, headers={"location": "https://evil.example/x"})

    with pytest.raises(FetchRefused):
        await _fetcher(elsewhere).fetch()
    assert seen == [MODEL_CHECK_HOST]

    def same_host(request):
        if request.url.path != MODEL_CHECK_URL.split(MODEL_CHECK_HOST)[1]:
            return httpx.Response(200, text="ok claude-opus-6")
        return httpx.Response(302, headers={"location": "/docs/en/models/other"})

    assert "claude-opus-6" in await _fetcher(same_host).fetch()
    with pytest.raises(FetchRefused):
        await _fetcher(lambda r: httpx.Response(200, content=b"x" * (MODEL_CHECK_MAX_BYTES + 1))).fetch()
    with pytest.raises(FetchRefused):
        await _fetcher(lambda r: httpx.Response(500, text="no")).fetch()


async def test_the_loop_waits_then_checks_every_day_and_stops_on_cancel(cfg):
    sleeps: list[float] = []
    fetcher = FakeFetcher(HTML)

    async def sleep(seconds):
        sleeps.append(seconds)
        if len(sleeps) == 3:
            raise asyncio.CancelledError

    check = ModelCheck(SeenModelStore(cfg), fetcher, sleep=sleep, interval_s=86_400, first_delay_s=600)
    with pytest.raises(asyncio.CancelledError):
        await check.loop()
    assert sleeps == [600, 86_400, 86_400] and fetcher.calls == 2


def _app(monkeypatch, tmp_path, **env):
    for key in ("ROOST_MODEL_CHECK", "ROOST_MODEL_CHECK_FILE"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return create_app()


def test_off_starts_no_loop(monkeypatch, tmp_path):
    app = _app(monkeypatch, tmp_path, ROOST_MODEL_CHECK="off", ROOST_MODEL_CHECK_FILE=str(FIXTURE))
    with TestClient(app):
        assert app.state.model_check_task is None


def test_scripted_mode_without_a_fixture_never_checks(monkeypatch, tmp_path):
    app = _app(monkeypatch, tmp_path)   # the suite runs ROOST_MODEL=scripted
    with TestClient(app):
        assert app.state.model_check_task is None


def test_the_fixture_file_is_used_only_in_scripted_mode(monkeypatch, tmp_path):
    scripted = load_config({"ROOST_DATA_DIR": str(tmp_path / "a"), "ROOST_MODEL": "scripted",
                            "ROOST_MODEL_CHECK_FILE": str(FIXTURE)})
    real = load_config({"ROOST_DATA_DIR": str(tmp_path / "b"), "ROOST_MODEL": "claude",
                        "ROOST_MODEL_CHECK_FILE": str(FIXTURE)})
    assert scripted.model_check_file == FIXTURE and real.model_check_file is None
    assert scripted.model_check == "on" and load_config(
        {"ROOST_DATA_DIR": str(tmp_path / "c"), "ROOST_MODEL_CHECK": "off"}).model_check == "off"
    with pytest.raises(ValueError):
        load_config({"ROOST_DATA_DIR": str(tmp_path / "d"), "ROOST_MODEL_CHECK": "sometimes"})


def test_a_scripted_gateway_with_a_fixture_starts_a_loop_that_is_cancelled_on_shutdown(monkeypatch, tmp_path):
    app = _app(monkeypatch, tmp_path, ROOST_MODEL_CHECK_FILE=str(FIXTURE))
    with TestClient(app):
        task = app.state.model_check_task
        assert task is not None and not task.done()
    assert task.cancelled() or task.done()


def test_a_scripted_gateway_with_a_fixture_makes_its_first_check_at_once(monkeypatch, tmp_path):
    app = _app(monkeypatch, tmp_path, ROOST_MODEL_CHECK_FILE=str(FIXTURE))
    with TestClient(app) as client:
        client.get("/api/health")
        seen: frozenset[str] = frozenset()
        for _ in range(50):
            seen = client.portal.call(app.state.seen_models.ids)
            if "claude-opus-6" in seen:
                break
            time.sleep(0.1)
        assert "claude-opus-6" in seen


async def test_a_file_fetcher_reads_the_fixture():
    assert "claude-opus-6" in await FilePageFetcher(FIXTURE).fetch()


async def test_the_notice_is_the_newest_undismissed(cfg):
    user = await register_user(cfg, "alice", "pw-123456")
    store = SeenModelStore(cfg)
    await store.add_new({"claude-opus-6": "Opus 6"})
    await store.add_new({"claude-sonnet-6": "Sonnet 6"})
    assert await store.newest_undismissed(user.id) == ("claude-sonnet-6", "Sonnet 6")
    await store.dismiss(user.id, "claude-sonnet-6")
    assert await store.newest_undismissed(user.id) == ("claude-opus-6", "Opus 6")
