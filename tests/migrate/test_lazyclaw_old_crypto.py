import sqlite3

import pytest

from lazyclaw_factory import (OLD_USER_ID, TEST_SECRET, add_user, enc_v1, new_db)
from roost.crypto.encryption import encrypt, user_aad
from roost.migrate.lazyclaw.old_crypto import (OldCryptoError, OldKeys, derive_legacy_key,
                                               load_old_keys)

DEK = bytes(range(32))


@pytest.fixture(scope="module")
def wrapped_db(tmp_path_factory):
    path = tmp_path_factory.mktemp("wrapped") / "lc.db"
    conn = new_db(path)
    add_user(conn, dek=DEK)
    yield conn
    conn.close()


def test_wrapped_user_unwraps(wrapped_db):
    with load_old_keys(wrapped_db, TEST_SECRET, None) as keys:
        assert keys.user_id == OLD_USER_ID
        assert keys.decrypt("enc-free text", "tasks.1.title") == "enc-free text"
        assert keys.decrypt(enc_v1("hello", DEK), "tasks.1.title") == "hello"


def test_wrong_secret_stops_without_leaking(wrapped_db):
    with pytest.raises(OldCryptoError) as err:
        load_old_keys(wrapped_db, "wrong-secret-xyz", None)
    assert "wrong-secret-xyz" not in str(err.value)
    assert "SERVER_SECRET" in str(err.value)


def test_legacy_null_dek_user(tmp_path):
    conn = new_db(tmp_path / "lc.db")
    legacy = derive_legacy_key(TEST_SECRET, "legacy-u")
    conn.execute("INSERT INTO users (id, username, password_hash, encryption_salt, encrypted_dek) "
                 "VALUES ('legacy-u','leg','x','s',NULL)")
    conn.commit()
    with load_old_keys(conn, TEST_SECRET, "leg") as keys:
        assert keys.decrypt(enc_v1("old", legacy), "t.1.title") == "old"


def test_multiple_users_need_a_username(tmp_path):
    conn = new_db(tmp_path / "lc.db")
    add_user(conn, dek=DEK, user_id="u1", username="a", salt="s1")
    add_user(conn, dek=DEK, user_id="u2", username="b", salt="s2")
    with pytest.raises(OldCryptoError, match="--old-username"):
        load_old_keys(conn, TEST_SECRET, None)
    with pytest.raises(OldCryptoError, match="No LazyClaw user"):
        load_old_keys(conn, TEST_SECRET, "nobody")


def test_no_users(tmp_path):
    conn = new_db(tmp_path / "lc.db")
    with pytest.raises(OldCryptoError, match="No LazyClaw user"):
        load_old_keys(conn, TEST_SECRET, None)


def test_strict_decrypt_stops(wrapped_db):
    keys = OldKeys(OLD_USER_ID, bytearray(DEK))
    with pytest.raises(OldCryptoError, match="tasks.t9.title"):
        keys.decrypt("[encrypted]", "tasks.t9.title")
    tampered = enc_v1("x", DEK)[:-4] + "AAAA"
    with pytest.raises(OldCryptoError, match="tasks.t9.title"):
        keys.decrypt(tampered, "tasks.t9.title")
    with pytest.raises(OldCryptoError):
        keys.decrypt(enc_v1("x", bytes(32)), "tasks.t9.title")
    keys.close()


def test_v2_tries_obvious_aads_and_counts_plain():
    keys = OldKeys(OLD_USER_ID, bytearray(DEK))
    token = encrypt("secret text", DEK, user_aad(OLD_USER_ID, "tasks:title"))
    assert keys.decrypt(token, "tasks.1.title", aad_context="tasks:title") == "secret text"
    plain_before = keys.plain_count
    assert keys.decrypt("plain", "tasks.1.title") == "plain"
    assert keys.plain_count == plain_before + 1
    assert keys.decrypt(None, "x") is None
    assert keys.decrypt("", "x") == ""
    bad = encrypt("s", DEK, user_aad(OLD_USER_ID, "other"))
    with pytest.raises(OldCryptoError):
        keys.decrypt(bad, "tasks.1.title", aad_context="tasks:title")


def test_close_zeroes_key():
    buf = bytearray(DEK)
    keys = OldKeys(OLD_USER_ID, buf)
    keys.close()
    assert bytes(buf) == bytes(32)
    with pytest.raises(OldCryptoError, match="closed"):
        keys.decrypt(enc_v1("x", DEK), "x")


# --- unlock by login password ------------------------------------------------------------

from lazyclaw_factory import OLD_USERNAME, insert  # noqa: E402
from roost.migrate.lazyclaw.old_crypto import load_old_keys_by_password, verify_keys  # noqa: E402

PW = "correct horse battery"


@pytest.fixture(scope="module")
def pw_db(tmp_path_factory):
    conn = new_db(tmp_path_factory.mktemp("pw") / "lc.db")
    add_user(conn, dek=DEK, password=PW)
    insert(conn, "tasks", id="t1", user_id=OLD_USER_ID, title=enc_v1("known", DEK))
    yield conn
    conn.close()


def test_password_unlock_matches_and_verifies(pw_db):
    with load_old_keys_by_password(pw_db, OLD_USERNAME, PW) as keys:
        assert keys.decrypt(enc_v1("hi", DEK), "t.1.title") == "hi"
        assert verify_keys(pw_db, keys) is True


def test_wrong_password_never_echoed(pw_db):
    with pytest.raises(OldCryptoError) as err:
        load_old_keys_by_password(pw_db, OLD_USERNAME, "nope-password-1")
    assert "nope-password-1" not in str(err.value) and "password" in str(err.value)


def test_unknown_user_and_missing_password_dek(tmp_path):
    conn = new_db(tmp_path / "lc.db")
    add_user(conn, dek=DEK)  # no password_encrypted_dek
    with pytest.raises(OldCryptoError, match="No LazyClaw user"):
        load_old_keys_by_password(conn, "ghost", PW)
    with pytest.raises(OldCryptoError, match="server-secret"):
        load_old_keys_by_password(conn, OLD_USERNAME, PW)


def test_password_key_that_does_not_open_the_data_is_refused(tmp_path):
    other = bytes(range(1, 33))
    conn = new_db(tmp_path / "lc.db")
    add_user(conn, dek=DEK, password=PW, pw_dek=other)  # password key differs from the data key
    insert(conn, "tasks", id="t1", user_id=OLD_USER_ID, title=enc_v1("known", DEK))
    with load_old_keys_by_password(conn, OLD_USERNAME, PW) as keys:
        with pytest.raises(OldCryptoError, match="does not open"):
            verify_keys(conn, keys)


def test_verify_with_no_ciphertext_returns_false(tmp_path):
    conn = new_db(tmp_path / "lc.db")
    add_user(conn, dek=DEK, password=PW)
    with load_old_keys(conn, TEST_SECRET, None) as keys:
        assert verify_keys(conn, keys) is False
