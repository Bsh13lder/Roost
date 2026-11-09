"""decrypt_field refuses a value that is not sealed, unless the caller allows legacy plaintext."""

import logging
import secrets

import pytest

from roost.crypto.encryption import PlaintextFieldError, decrypt_field, encrypt_field, user_aad


@pytest.fixture
def key() -> bytes:
    return secrets.token_bytes(32)


def test_plaintext_is_refused_by_default(key, caplog):
    aad = user_aad("u1", "tasks:title")
    with caplog.at_level(logging.ERROR), pytest.raises(PlaintextFieldError):
        decrypt_field("secret plain text", key, aad)
    assert "tasks:title" in caplog.text
    assert "secret plain text" not in caplog.text


def test_plaintext_error_message_never_holds_the_value(key):
    with pytest.raises(PlaintextFieldError) as exc:
        decrypt_field("secret plain text", key, user_aad("u1", "notes:body"))
    assert "secret plain text" not in str(exc.value)
    assert "notes:body" in str(exc.value)


def test_allow_plaintext_passes_legacy_value_through(key):
    assert decrypt_field("legacy", key, allow_plaintext=True) == "legacy"


def test_sealed_values_and_none_are_unchanged(key):
    aad = user_aad("u1", "notes:body")
    assert decrypt_field(encrypt_field("hello", key, aad), key, aad) == "hello"
    assert decrypt_field(None, key, aad) is None
