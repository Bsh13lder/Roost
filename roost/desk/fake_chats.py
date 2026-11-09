""""Fake chats": a scripted WhatsApp-like page for the fast-pages tests and E2E (``ROOST_FAKE_SCREEN=chats``).

The search box is a contenteditable ``div`` named "Search or start a new chat" with no ``role=searchbox``, no
``type=search``, no search landmark and no form (as WhatsApp Web's is), so only its words say it is a search box.
Typing into it shows the "Francis Dentist" chat; opening that chat shows a long message pane (an area whose text runs
far past what its box shows, so reading it by scrolling would take dozens of steps), a composer, a link to a PDF
that the bot's browser can fetch, and a link to a PDF behind a ``blob:`` address (as WhatsApp Web shows a chat's
document), read inside the page. The appointment sits deep in the pane, and in the PDF.
"""

from __future__ import annotations

from collections.abc import Mapping

from roost.desk.fake_cu import FakeScreenState, fake_area, fake_target, script

CHATS_HOST = "web.whatsapp.test"
CHATS_URL = f"https://{CHATS_HOST}/"
PDF_URL = f"https://{CHATS_HOST}/docs/cita.pdf"
APPOINTMENT_LINE = "Francis: Your appointment is Thursday 14 November at 10:30, Clinica Sol."
PDF_LINE = "Cita: jueves 14 de noviembre, 10:30, Clinica Sol"
BLOB_PDF_URL = f"blob:https://{CHATS_HOST}/8d0c5a2e-4b7f-4e61-9c3a-2f1e6b9d7a40"
BLOB_PDF_LINE = "Receta: ibuprofeno 600 mg, cada 8 horas, 3 dias"
FILLER_LINES = 400


def tiny_pdf(text: str) -> bytes:
    """A one-page PDF that says ``text`` (Helvetica, no images): enough for pypdf and pdfplumber."""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = (
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    )
    out, offsets = b"%PDF-1.4\n", []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets)
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return out


def _messages() -> str:
    early = [f"Francis: reminder {n}, bring your card and arrive ten minutes early." for n in range(FILLER_LINES // 2)]
    late = [f"You: thanks, noted {n}." for n in range(FILLER_LINES // 2)]
    return "\n".join([*early, APPOINTMENT_LINE, *late])


SEARCH = fake_target("field", "Search or start a new chat", 20, 70, width=380, tag="div", search_named=True)
_ROWS = (
    fake_target("row", "Mum", 20, 130, width=380, height=60),
    fake_target("row", "Work group", 20, 190, width=380, height=60),
)
_FRANCIS = fake_target("row", "Francis Dentist", 20, 130, width=380, height=60)
_COMPOSER = fake_target("field", "Type a message", 420, 640, width=820, tag="div")
_PDF_LINK = fake_target("link", "Cita.pdf", 440, 580, width=160, tag="a", link_host=CHATS_HOST)
_BLOB_LINK = fake_target("link", "Receta.pdf", 620, 580, width=160, tag="a")
_LIST_TEXT = "Mum\nWork group\nFrancis Dentist\n" + "\n".join(f"Contact {n}" for n in range(40))
CHAT_LIST = fake_area("grid", "Chat list", _LIST_TEXT, 0, 120, 400, 560)
MESSAGES = fake_area("application", "Messages", _messages(), 400, 60, 880, 560)


def _chats(name: str, targets: tuple, text: str, **leads) -> tuple[str, FakeScreenState]:
    return name, FakeScreenState(url=CHATS_URL, title="WhatsApp", targets=targets, text=text, **leads)


FAKE_CHATS: Mapping[str, FakeScreenState] = script([
    _chats("home", (SEARCH, *_ROWS), "WhatsApp", areas=(CHAT_LIST,), on_type="found"),
    _chats("found", (SEARCH, _FRANCIS), "WhatsApp. Search results.", areas=(CHAT_LIST,),
           on_click={"Francis Dentist": "chat"}),
    _chats("chat", (SEARCH, _FRANCIS, _PDF_LINK, _COMPOSER, _BLOB_LINK), "WhatsApp. Francis Dentist.",
           areas=(CHAT_LIST, MESSAGES), link_urls={"Cita.pdf": PDF_URL, "Receta.pdf": BLOB_PDF_URL},
           files={PDF_URL: tiny_pdf(PDF_LINE), BLOB_PDF_URL: tiny_pdf(BLOB_PDF_LINE)}),
])
