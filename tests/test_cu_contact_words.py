"""Owner, 2026-11-03: Gigs' Upwork cover letter was flagged as contact details for "Node.js", "ASP.NET" and
"Budget: 1500 - 2000 USD". A number range or an amount is not a phone. Since the same day only an email address or
a phone number is a contact detail (links, domains and @handles are not), and secrets always flag."""

from __future__ import annotations

import pytest

from roost.computer_use.contact import has_contact
from roost.computer_use.text_source import text_flags

_PROPOSAL = (
    "Hi! I have built REST APIs in Node.js and ASP.NET for six years, and front ends in Vue.js and React.\n"
    "Budget: 1500 - 2000 USD. I can start on 2026-11-04 and deliver milestone 1 in 10-14 days for $1,500.\n"
    "Tools: Next.js, Express.js, D3.js, setup.py, ADO.NET, VB.NET."
)


@pytest.mark.parametrize("text", [
    "Node.js", "ASP.NET", "Vue.js", "I use Next.js and Three.js", "ADO.NET and VB.NET", "edit setup.py",
    "Budget: 1500 - 2000 USD", "between 10000 - 20000 EUR", "$1,500", "€ 12000000", "1500-2000", "10 - 14 days",
    "budget 150000 - 250000", "on 2026-11-04", "python 3.12 jobs", "version 1.2.3.4", _PROPOSAL,
])
def test_ordinary_proposal_words_are_not_contact(text: str) -> None:
    assert not has_contact(text)
    assert text_flags(text) == frozenset()


@pytest.mark.parametrize("text", [
    "write to ana@example.com", "call +34 612 345 678", "my phone 612345678",
    "(555) 123-4567 ext", "+1 555 123 4567", "+34-612-345-678",
])
def test_real_contact_details_still_flag(text: str) -> None:
    assert has_contact(text)
    assert "contact" in text_flags(text)


def test_a_proposal_with_an_email_still_flags() -> None:
    assert text_flags(_PROPOSAL + " Write to me at gigs@example.com") == frozenset({"contact"})


def test_secrets_flag_whatever_else_the_text_holds() -> None:
    assert "secret" in text_flags("Node.js dev, my password is hunter2!")
    assert "secret" in text_flags("4111 1111 1111 1111")
