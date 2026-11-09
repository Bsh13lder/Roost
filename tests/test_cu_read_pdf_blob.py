"""read_pdf reads a PDF behind a ``blob:`` address (WhatsApp Web shows a chat's PDF that way): the bytes are read
inside the page that owns the blob, in an isolated world (``Runtime.evaluate``: fetch → base64, size-capped in the
page before any copy), into memory only, then read by the same capped pdfplumber path. Only a blob of the page's own
origin is read; another origin's blob, and anything not blob:/http(s), is refused."""

from __future__ import annotations

import base64
import html
import json
from dataclasses import replace
from typing import Any

import pytest

from roost.computer_use.texts import PDF_BLOB_OFF_SITE_TEXT, PDF_NO_ADDRESS_TEXT, PDF_TOO_BIG_TEXT
from roost.config import load_config
from roost.constants import CU_PDF_MAX_BYTES
from roost.db.connection import init_db
from roost.desk.blob_fetch import BLOB_WORLD, blob_origin, is_blob_url, page_origin, read_blob
from roost.desk.cdp import CdpReplyError
from roost.desk.fake_chats import BLOB_PDF_LINE, BLOB_PDF_URL, CHATS_URL, FAKE_CHATS, PDF_LINE, tiny_pdf
from roost.desk.fake_cu import FakeScreenState, fake_target, script
from roost.desk.page_fetch import FetchFailed, FileTooBig

from cu_run_helpers import make_cu_rig, run_step, step

MESSAGE = "Find my appointment with Francis on WhatsApp"
BLOB = "blob:https://web.whatsapp.test/5b1c0f3e-1d2a-4c55-9a77-0d6c2b8e4f10"


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


# -- the addresses ----------------------------------------------------------------------------------------------


def test_a_blob_origin_is_its_inner_web_origin():
    assert is_blob_url(BLOB) and not is_blob_url("https://web.whatsapp.test/x")
    assert blob_origin(BLOB) == "https://web.whatsapp.test"
    assert blob_origin("blob:https://Web.WhatsApp.test:443/abc") == "https://web.whatsapp.test"
    assert blob_origin("blob:http://example.test:8080/abc") == "http://example.test:8080"


@pytest.mark.parametrize("url", ["blob:null/abc", "blob:file:///etc/passwd", "blob:data:text/plain,hi",
                                 "blob:chrome-extension://abc/def", "https://web.whatsapp.test/x", "blob:", "blob:/x"])
def test_a_blob_with_no_web_origin_has_none(url):
    assert blob_origin(url) == ""


def test_a_pages_origin_is_its_own_or_its_blobs():
    assert page_origin("https://web.whatsapp.test/chat?x=1") == "https://web.whatsapp.test"
    assert page_origin(BLOB) == "https://web.whatsapp.test"
    assert page_origin("data:text/html,hi") == "" and page_origin("about:blank") == ""


# -- reading it in the page -------------------------------------------------------------------------------------


class _Cdp:
    """Answers the isolated world and the one evaluate with ``value`` (or raises on ``refuse``)."""

    def __init__(self, value: Any = None, *, exception: bool = False, refuse: str = "") -> None:
        self.value, self.exception, self.refuse = value, exception, refuse
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def send(self, method: str, params: dict[str, Any] | None = None, session_id: str | None = None) -> dict:
        params = params or {}
        self.calls.append((method, params))
        if method == self.refuse:
            raise CdpReplyError("refused")
        if method == "Page.getFrameTree":
            return {"result": {"frameTree": {"frame": {"id": "F1"}}}}
        if method == "Page.createIsolatedWorld":
            return {"result": {"executionContextId": 7}}
        if method == "Runtime.evaluate":
            result: dict[str, Any] = {"result": {"type": "object", "value": self.value}}
            if self.exception:
                result["exceptionDetails"] = {"text": "Uncaught TypeError: Failed to fetch"}
            return {"result": result}
        return {"result": {}}

    def evaluated(self) -> dict[str, Any]:
        return next(p for m, p in self.calls if m == "Runtime.evaluate")


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


async def test_a_blob_is_read_in_the_pages_isolated_world_into_memory():
    pdf = tiny_pdf(PDF_LINE)
    client = _Cdp({"data": _b64(pdf)})
    assert await read_blob(client, "S1", BLOB, 10_000) == pdf
    world = next(p for m, p in client.calls if m == "Page.createIsolatedWorld")
    assert world == {"frameId": "F1", "worldName": BLOB_WORLD}
    call = client.evaluated()
    assert call["contextId"] == 7 and call["awaitPromise"] is True and call["returnByValue"] is True
    assert json.dumps(BLOB) in call["expression"] and "10000" in call["expression"]   # the cap is checked in the page
    assert "Network.loadNetworkResource" not in [m for m, _ in client.calls]


async def test_a_blob_the_page_says_is_too_big_is_never_copied():
    with pytest.raises(FileTooBig):
        await read_blob(_Cdp({"tooBig": True}), "S1", BLOB, 10_000)


async def test_an_answer_past_the_cap_is_refused_before_decoding(monkeypatch):
    def no_decode(*args, **kwargs):
        raise AssertionError("decoded past the cap")

    monkeypatch.setattr("roost.desk.blob_fetch.base64.b64decode", no_decode)
    with pytest.raises(FileTooBig):
        await read_blob(_Cdp({"data": "A" * 20_000}), "S1", BLOB, 10_000)


@pytest.mark.parametrize("client", [
    _Cdp({"data": "%%% not base64 %%%"}), _Cdp({"error": "gone"}), _Cdp("a string"), _Cdp(None),
    _Cdp({"data": _b64(b"%PDF")}, exception=True), _Cdp(refuse="Runtime.evaluate"),
    _Cdp(refuse="Page.createIsolatedWorld"),
])
async def test_a_blob_that_cant_be_read_is_a_failed_fetch(client):
    with pytest.raises(FetchFailed):
        await read_blob(client, "S1", BLOB, 10_000)


@pytest.mark.parametrize("url", ["https://web.whatsapp.test/x.pdf", "blob:null/abc", "blob:file:///x"])
async def test_only_a_web_origin_blob_is_read(url):
    client = _Cdp({"data": _b64(b"%PDF")})
    with pytest.raises(FetchFailed):
        await read_blob(client, "S1", url, 10_000)
    assert client.calls == []


# -- in the loop ------------------------------------------------------------------------------------------------


async def _chat(cfg, screen=FAKE_CHATS, state: str = "chat", username: str = "alice"):
    rig = await make_cu_rig(cfg, MESSAGE, screen=screen, username=username)
    rig.page.state_name = state
    return rig


async def test_read_pdf_reads_a_blob_link_in_the_chat_and_taints(cfg):
    rig = await _chat(cfg)
    runner = rig.tool_runner(tainted=False)
    looked = html.unescape(await run_step(runner, "look", picture=False))
    assert '[5] link "Receta.pdf"' in looked
    runner.tainted = False
    read = await run_step(runner, "read_pdf", index=5)
    assert runner.tainted and read.startswith("<untrusted_page") and BLOB_PDF_LINE in html.unescape(read)
    assert rig.page.blobs_read == (BLOB_PDF_URL,) and rig.page.fetched == () and rig.desk.inputs == ()


async def test_read_pdf_reads_a_blob_pdf_open_in_the_tab(cfg):
    viewer = script([("pdf", FakeScreenState(url=BLOB, title="cita.pdf", files={BLOB: tiny_pdf(PDF_LINE)}))])
    rig = await _chat(cfg, viewer, "pdf")
    cu = rig.computer()
    await step(cu, "look", picture=False)
    read = await step(cu, "read_pdf")
    assert read.looked and PDF_LINE in html.unescape(read.text) and rig.page.blobs_read == (BLOB,)


async def test_read_pdf_refuses_another_origins_blob(cfg):
    other = "blob:https://evil.example/0f0f"
    link = fake_target("link", "Cita.pdf", 40, 100, tag="a")
    page = script([("p", FakeScreenState(url=CHATS_URL, title="W", targets=(link,), link_urls={"Cita.pdf": other},
                                         files={other: tiny_pdf(PDF_LINE)}))])
    rig = await _chat(cfg, page, "p")
    cu = rig.computer()
    await step(cu, "look", picture=False)
    assert (await step(cu, "read_pdf", index=1)).text == PDF_BLOB_OFF_SITE_TEXT.format(host="evil.example")
    assert rig.page.blobs_read == () and rig.page.fetched == ()


async def test_read_pdf_refuses_a_blob_with_no_web_origin_and_other_schemes(cfg):
    for url in ("blob:null/abc", "data:application/pdf;base64,JVBERi0=", "file:///home/bot/cita.pdf"):
        tab = script([("t", FakeScreenState(url=url, title="cita.pdf", files={url: tiny_pdf(PDF_LINE)}))])
        rig = await _chat(cfg, tab, "t", username=f"u{abs(hash(url)) % 10_000}")
        cu = rig.computer()
        await step(cu, "look", picture=False)
        assert (await step(cu, "read_pdf")).text == PDF_NO_ADDRESS_TEXT
        assert rig.page.blobs_read == () and rig.page.fetched == ()


async def test_read_pdf_refuses_an_oversize_blob(cfg):
    big = {**FAKE_CHATS["chat"].files, BLOB_PDF_URL: b"%PDF" + b"x" * (CU_PDF_MAX_BYTES + 1)}
    screen = script([("chat", replace(FAKE_CHATS["chat"], files=big))])
    rig = await _chat(cfg, screen)
    cu = rig.computer()
    await step(cu, "look", picture=False)
    assert (await step(cu, "read_pdf", index=5)).text == PDF_TOO_BIG_TEXT
