"""The secret filter (memory Task 3): nothing that looks like a password, code, key or card is kept."""

from __future__ import annotations

import pytest

from roost.memory.secrets import SECRET_REFUSAL_TEXT, looks_secret


@pytest.mark.parametrize("text", [
    "my password is hunter2",
    "api key: sk-abc123def456",
    "the code is 482913",
    "card 4111 1111 1111 1111",
    "IBAN ES91 2100 0418 4502 0005 1332",
    "wifi is a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6",
    "AKIAABCDEFGHIJKLMNOP",
    # Security review (memory Task 10): a few words between the keyword and the value, Spanish,
    # no verb at all, and the digits before the word.
    "password for gmail is hunter2",
    "wifi password hunter2",
    "mi contraseña es hunter2",
    "La contraseña de gmail es hunter2",
    "la clave del banco es 1234abcd",
    "el código es 482913",
    "482913 is the code",
])
def test_secrets_are_refused_in_every_shape(text):
    assert looks_secret(text)


@pytest.mark.parametrize("text", [
    "Ana's birthday is in May",
    "I prefer short answers",
    "Call Marta at 9 on 12 May",
    "Flat 4B, 3rd floor",
    "My PIN pad is broken",
    "16 digits that fail Luhn: 1234 5678 9012 3456",
    "I use a password manager",
    "Mi cumpleaños es el 3 de mayo",
])
def test_ordinary_facts_pass(text):
    assert not looks_secret(text)


def test_the_refusal_is_a_plain_sentence():
    assert SECRET_REFUSAL_TEXT.endswith("never kept in memory.")
