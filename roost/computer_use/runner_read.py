"""Reading the page without looking at it (fast pages, slices 3 and 5): ``read_text`` and ``read_pdf``.

``ComputerUse`` (``roost/computer_use/runner.py``) mixes this in. A read moves nothing on the screen, so the newest
look's numbers still hold afterwards. What it returns is page content: escaped in ``<untrusted_page>``
(``roost/computer_use/read_text.py``) and ``looked`` (the run is tainted, as by a look).

``read_pdf`` fetches through the bot's own browser (``roost/desk/page_fetch.py``: its cookies, its egress, into
memory only), and only an address ``check_url`` accepts on the page's own site or the run's fence. A ``blob:`` PDF
(WhatsApp Web's, in a chat or open in the tab) has no address to fetch again, so it is read inside the page that owns
it (``roost/desk/blob_fetch.py``), and only when its origin is that page's own. The PDF's text is read with caps
(``roost/computer_use/pdf_text.py``)."""

from __future__ import annotations

from roost.computer_use import aim
from roost.computer_use import session as loop
from roost.computer_use.lines import act_line
from roost.computer_use.marks import same_page
from roost.computer_use.models import ReadPdfIn, ReadTextIn
from roost.computer_use.outcome import CuOutcome
from roost.computer_use.pdf_text import PdfUnreadable, pdf_text
from roost.computer_use.read_text import read_reply
from roost.computer_use.texts import (
    NO_AREA_TEXT, PDF_BLOB_OFF_SITE_TEXT, PDF_FAILED_TEXT, PDF_NO_ADDRESS_TEXT, PDF_NOT_A_LINK_TEXT, PDF_NOT_PDF_TEXT, PDF_OFF_SITE_TEXT,
    PDF_TOO_BIG_TEXT, PDF_UNREADABLE_TEXT, STALE_AREA_TEXT,
)
from roost.constants import CU_PDF_MAX_BYTES
from roost.desk.blob_fetch import blob_origin, is_blob_url, page_origin
from roost.desk.page_fetch import FetchFailed, FileTooBig
from roost.desk.stuck import host_of_url
from roost.desk.url_policy import UrlBlocked, check_url
from roost.documents.pdf_ops import is_pdf

LINK_KIND = "link"


class PageReading:
    """Mixed into ``ComputerUse``: every attribute it reads (``_desk``, ``_marks``, ``state``…) is the runner's."""

    async def _read_text(self, args: ReadTextIn) -> CuOutcome:
        page = self._desk.page()
        url = await page.url()
        node_id, what, again = None, "Page text", "read_text"
        if args.area is not None:
            area = self._marks.area(args.area)
            if area is None:
                return CuOutcome(NO_AREA_TEXT.format(index=args.area))
            if not same_page(self._marks.url, url):
                return CuOutcome(STALE_AREA_TEXT.format(index=args.area))
            node_id, what = area.node_id, f"Area {args.area} ({area.role} \"{area.name}\")"
            again = f"read_text area={args.area}"
        text = await page.area_text(node_id)
        if text is None:
            return CuOutcome(STALE_AREA_TEXT.format(index=args.area))
        return await self._read_done("read_text", url, what, text, args.start, args.find, again)

    async def _read_done(self, tool: str, url: str, what: str, text: str, start: int, find: str | None,
                         again: str) -> CuOutcome:
        await self._announce(act_line(tool, None, {}))
        self.state = loop.after_read(self.state)
        return CuOutcome(read_reply(url, what, text, start=start, find=find, again=again), url=url, looked=True)

    async def _pdf_address(self, args: ReadPdfIn, page_url: str) -> tuple[str, str]:
        """The PDF's address (a numbered link's, or the open tab's), or "" and the sentence why not."""
        if args.index is None:
            return page_url, ""
        target, why = await aim.indexed(self._desk.page(), self._marks, args.index, page_url)
        if why:
            return "", why
        if target is None or target.kind != LINK_KIND:
            return "", PDF_NOT_A_LINK_TEXT
        return await self._desk.page().link_url(target.node_id), ""

    def _pdf_refusal(self, url: str, page_url: str) -> str:
        """Only a web address the URL policy accepts, on the page's own site or the run's fence, or a blob of the
        page's own origin."""
        if is_blob_url(url):
            return _blob_refusal(url, page_url)
        try:
            checked = check_url(url)
        except UrlBlocked:
            return PDF_NO_ADDRESS_TEXT
        host = host_of_url(checked)
        if host != host_of_url(page_url) and (self._fence is None or not self._fence.allows(host)):
            return PDF_OFF_SITE_TEXT.format(host=host)
        return ""

    async def _read_pdf(self, args: ReadPdfIn) -> CuOutcome:
        page = self._desk.page()
        page_url = await page.url()
        url, why = await self._pdf_address(args, page_url)
        why = why or self._pdf_refusal(url, page_url)
        if why:
            return CuOutcome(why)
        try:
            read = page.read_blob if is_blob_url(url) else page.fetch
            data = await read(url, CU_PDF_MAX_BYTES)
        except FileTooBig:
            return CuOutcome(PDF_TOO_BIG_TEXT)
        except FetchFailed as exc:
            return CuOutcome(PDF_FAILED_TEXT.format(why=exc))
        if not is_pdf(data):
            return CuOutcome(PDF_NOT_PDF_TEXT)
        try:
            text = await pdf_text(data)
        except PdfUnreadable as exc:
            return CuOutcome(PDF_UNREADABLE_TEXT.format(why=exc))
        again = f"read_pdf index={args.index}" if args.index is not None else "read_pdf"
        return await self._read_done("read_pdf", url, "PDF text", text, args.start, args.find, again)


def _blob_refusal(url: str, page_url: str) -> str:
    """A ``blob:`` PDF is read only when it has a web origin the URL policy accepts and it is the page's own."""
    origin = blob_origin(url)
    try:
        check_url(origin)
    except UrlBlocked:
        return PDF_NO_ADDRESS_TEXT
    if origin != page_origin(page_url):
        return PDF_BLOB_OFF_SITE_TEXT.format(host=host_of_url(origin))
    return ""
