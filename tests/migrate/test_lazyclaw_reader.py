import pytest

from lazyclaw_factory import OLD_USER_ID, OLD_USERNAME, SAMPLE_PASSWORD, build_sample, enc_v1, insert, new_db, add_user
from roost.migrate.lazyclaw.old_crypto import OldCryptoError, load_old_keys_by_password
from roost.migrate.lazyclaw.reader import read_lazyclaw


@pytest.fixture(scope="module")
def sample(tmp_path_factory):
    import sqlite3
    path = build_sample(tmp_path_factory.mktemp("s") / "lc.db")
    conn = sqlite3.connect(path)
    yield conn
    conn.close()


def test_reads_and_decrypts_only_this_users_rows(sample):
    insert(sample, "tasks", id="other", user_id="someone-else", title="not mine")
    with load_old_keys_by_password(sample, OLD_USERNAME, SAMPLE_PASSWORD) as keys:
        data = read_lazyclaw(sample, keys)
    assert {r["id"] for r in data.tasks} == {"t1", "t2", "t3", "t4"}
    assert {r["title"] for r in data.tasks if r["id"] == "t1"} == {"Buy kitchen tiles from the big shop"}
    assert {r["name"] for r in data.projects} == {"General", "Kitchen", "Trip to Lisbon"}
    assert len(data.expenses) == 5 and len(data.topups) == 1 and len(data.recurring) == 2
    assert data.settings_timezone == "Europe/Madrid"
    assert next(r for r in data.expenses if r["id"] == "e1")["amount"] == 25.5


def test_undecryptable_value_stops_with_the_row_not_the_text(tmp_path):
    from lazyclaw_factory import SAMPLE_DEK
    conn = new_db(tmp_path / "x.db")
    add_user(conn, dek=SAMPLE_DEK, password=SAMPLE_PASSWORD)
    insert(conn, "tasks", id="bad", user_id=OLD_USER_ID, title=enc_v1("secret words", bytes(32)))
    with load_old_keys_by_password(conn, OLD_USERNAME, SAMPLE_PASSWORD) as keys:
        with pytest.raises(OldCryptoError) as err:
            read_lazyclaw(conn, keys)
    assert "tasks.bad.title" in str(err.value) and "secret words" not in str(err.value)
