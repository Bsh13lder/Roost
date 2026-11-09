"""Fast pages, slice 5: read_pdf reads a PDF the bot has open, or one a page links to, as text in one step. The bot's
own browser fetches it (its cookies, its egress), only from the page's own site or the run's fence; the bytes stay
in memory, the text is escaped untrusted page text and taints the run; size, pages and time are capped."""

from __future__ import annotations

import asyncio
import base64
import html
from dataclasses import replace
from typing import Any

import pytest

from roost.computer_use.pdf_text import PdfUnreadable, pdf_text
from roost.computer_use.texts import (
    PDF_NOT_A_LINK_TEXT, PDF_NOT_PDF_TEXT, PDF_NO_ADDRESS_TEXT, PDF_OFF_SITE_TEXT, PDF_TOO_BIG_TEXT,
)
from roost.config import load_config
from roost.constants import CU_PDF_MAX_BYTES, CU_PDF_PAGES_MAX
from roost.db.connection import init_db
from roost.desk.fake_chats import FAKE_CHATS, PDF_LINE, PDF_URL, tiny_pdf
from roost.desk.fake_cu import FakeScreenState, fake_target, script
from roost.desk.page_fetch import FetchFailed, FileTooBig, fetch_through_browser

from cu_run_helpers import make_cu_rig, run_step, step

MESSAGE = "Find my appointment with Francis on WhatsApp"


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


async def _rig(cfg, screen=FAKE_CHATS, state: str = "chat"):
    rig = await make_cu_rig(cfg, MESSAGE, screen=screen)
    rig.page.state_name = state
    return rig


# -- the text ---------------------------------------------------------------------------------------------------


async def test_pdf_text_reads_the_words():
    assert PDF_LINE in await pdf_text(tiny_pdf(PDF_LINE))


async def test_something_that_is_not_a_pdf_is_unreadable():
    with pytest.raises(PdfUnreadable):
        await pdf_text(b"<html>not a pdf</html>")
    with pytest.raises(PdfUnreadable):
        await pdf_text(b"%PDF-1.4 broken")


async def test_only_the_first_pages_are_read(monkeypatch):
    seen: list[int] = []

    class _Page:
        def __init__(self, n: int) -> None:
            self.n = n

        def extract_text(self) -> str:
            seen.append(self.n)
            return f"page {self.n}"

    class _Pdf:
        pages = [_Page(n) for n in range(CU_PDF_PAGES_MAX + 5)]

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr("roost.computer_use.pdf_text._open", lambda data: _Pdf())
    text = await pdf_text(b"%PDF-1.4 fake")
    assert len(seen) == CU_PDF_PAGES_MAX and f"page {CU_PDF_PAGES_MAX - 1}" in text and "more pages" in text


# -- fetching through the browser -------------------------------------------------------------------------------


class _Cdp:
    def __init__(self, data: bytes, *, status: int = 200, success: bool = True) -> None:
        self.data, self.status, self.success = data, status, success
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.offset = 0

    async def send(self, method: str, params: dict[str, Any] | None = None, session_id: str | None = None) -> dict:
        params = params or {}
        self.calls.append((method, params))
        if method == "Page.getFrameTree":
            return {"result": {"frameTree": {"frame": {"id": "F1"}}}}
        if method == "Network.loadNetworkResource":
            return {"result": {"resource": {"success": self.success, "httpStatusCode": self.status, "stream": "S9"}}}
        if method == "IO.read":
            chunk = self.data[self.offset:self.offset + min(params["size"], 4096)]   # Chromium's chunks are small
            self.offset += len(chunk)
            return {"result": {"base64Encoded": True, "data": base64.b64encode(chunk).decode(),
                               "eof": self.offset >= len(self.data)}}
        return {"result": {}}

    def methods(self) -> list[str]:
        return [m for m, _ in self.calls]


async def test_the_browser_fetches_the_file_into_memory_and_closes_the_stream():
    client = _Cdp(b"%PDF" + b"x" * 5000)
    data = await fetch_through_browser(client, "S1", PDF_URL, 10_000)
    assert data == client.data
    load = next(p for m, p in client.calls if m == "Network.loadNetworkResource")
    assert load["url"] == PDF_URL and load["frameId"] == "F1" and load["options"]["includeCredentials"]
    assert client.methods()[-1] == "IO.close" and "Runtime.evaluate" not in client.methods()


async def test_a_file_past_the_cap_is_not_read_to_the_end():
    client = _Cdp(b"%PDF" + b"x" * 50_000)
    with pytest.raises(FileTooBig):
        await fetch_through_browser(client, "S1", PDF_URL, 10_000)
    assert client.offset < 50_000 and client.methods()[-1] == "IO.close"


async def test_an_http_error_is_a_failed_fetch():
    with pytest.raises(FetchFailed):
        await fetch_through_browser(_Cdp(b"", status=404), "S1", PDF_URL, 10_000)
    with pytest.raises(FetchFailed):
        await fetch_through_browser(_Cdp(b"", success=False), "S1", PDF_URL, 10_000)


# -- in the loop -----------------------------------------------------------------------------------------------


async def test_read_pdf_by_the_links_number_reads_it_in_one_step_and_taints(cfg):
    rig = await _rig(cfg)
    runner = rig.tool_runner(tainted=False)
    looked = html.unescape(await run_step(runner, "look", picture=False))
    assert '[3] link "Cita.pdf"' in looked
    runner.tainted = False
    read = await run_step(runner, "read_pdf", index=3)
    assert runner.tainted and read.startswith("<untrusted_page") and PDF_LINE in html.unescape(read)
    assert rig.page.fetched == (PDF_URL,) and rig.desk.inputs == ()


async def test_read_pdf_of_the_open_tab_needs_no_number(cfg):
    viewer = script([("pdf", FakeScreenState(url=PDF_URL, title="cita.pdf", files={PDF_URL: tiny_pdf(PDF_LINE)}))])
    rig = await _rig(cfg, viewer, "pdf")
    cu = rig.computer()
    await step(cu, "look", picture=False)
    read = await step(cu, "read_pdf")
    assert read.looked and PDF_LINE in html.unescape(read.text)


async def test_read_pdf_refuses_a_control_that_is_no_link(cfg):
    rig = await _rig(cfg)
    cu = rig.computer()
    await step(cu, "look", picture=False)
    assert (await step(cu, "read_pdf", index=1)).text == PDF_NOT_A_LINK_TEXT
    assert rig.page.fetched == ()


async def test_read_pdf_refuses_another_site_off_the_fence(cfg):
    other = "https://files.elsewhere.example/cita.pdf"
    link = fake_target("link", "Cita.pdf", 40, 100, tag="a", link_host="files.elsewhere.example")
    page = script([("p", FakeScreenState(url="https://web.whatsapp.test/", title="W", targets=(link,),
                                         link_urls={"Cita.pdf": other}, files={other: tiny_pdf(PDF_LINE)}))])
    rig = await _rig(cfg, page, "p")
    cu = rig.computer()
    await step(cu, "look", picture=False)
    assert (await step(cu, "read_pdf", index=1)).text == PDF_OFF_SITE_TEXT.format(host="files.elsewhere.example")
    assert rig.page.fetched == ()


async def test_read_pdf_without_a_web_address_says_so(cfg):
    blob = script([("b", FakeScreenState(url="data:application/pdf;base64,JVBERi0=", title="cita.pdf"))])
    rig = await _rig(cfg, blob, "b")
    cu = rig.computer()
    await step(cu, "look", picture=False)
    assert (await step(cu, "read_pdf")).text == PDF_NO_ADDRESS_TEXT


async def test_read_pdf_of_something_else_or_too_big_says_so(cfg):
    page = replace(FAKE_CHATS["chat"], files={PDF_URL: b"<html>sign in</html>"})
    rig = await _rig(cfg, script([("chat", page)]), "chat")
    cu = rig.computer()
    await step(cu, "look", picture=False)
    assert (await step(cu, "read_pdf", index=3)).text == PDF_NOT_PDF_TEXT
    big = replace(FAKE_CHATS["chat"], files={PDF_URL: b"%PDF" + b"x" * (CU_PDF_MAX_BYTES + 1)})
    rig2 = await make_cu_rig(cfg, MESSAGE, screen=script([("chat", big)]), username="bob")
    cu2 = rig2.computer()
    await step(cu2, "look", picture=False)
    assert (await step(cu2, "read_pdf", index=3)).text == PDF_TOO_BIG_TEXT


async def test_a_pdf_that_takes_too_long_is_given_up(cfg, monkeypatch):
    monkeypatch.setattr("roost.computer_use.pdf_text.CU_PDF_PARSE_TIMEOUT_S", 0.01)

    def slow(data: bytes) -> str:
        import time
        time.sleep(0.2)
        return "late"

    monkeypatch.setattr("roost.computer_use.pdf_text._extract", slow)
    with pytest.raises(PdfUnreadable):
        await pdf_text(tiny_pdf(PDF_LINE))
    await asyncio.sleep(0.25)
