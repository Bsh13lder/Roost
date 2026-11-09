"""Owner, 2026-10-29: "why asks hard floor?" Adding a step to a task asked, because the task's own id (a UUID)
looked like a secret token. A record's id names a thing; it is never the user's secret."""

import pytest

from roost.approvals.floor import hard_floor
from roost.approvals.models import ApprovalState

STATE = ApprovalState("auto_edit", frozenset(), True)
TASK_ID = "3dbb7cc4-67c1-47c5-813c-9b40f63411b4"


@pytest.mark.parametrize(("name", "arguments"), [
    ("add_step", {"task": TASK_ID, "title": "Valid passport"}),
    ("add_comment", {"task": "c9929a13-8430-4535-8e21-8e84c724ca8c", "text": "all good, meeting went perfect"}),
    ("forget", {"memory_id": "0b6f3a1c-e838-428d-9294-4b0960eb1a9a"}),
    ("update_step", {"task": TASK_ID, "step_id": "ce67e538-d8b0-4759-a66d-7a19d3fd7ccf", "done": True}),
])
def test_a_record_id_is_not_a_secret(name, arguments):
    assert hard_floor(name, arguments, STATE) is None


@pytest.mark.parametrize("text", [
    "my api key is sk-abcdef1234567890",
    "token: ghp_abcdefgh12345678",
    f"key {TASK_ID}",                      # inside your words a UUID-shaped string still counts
    "zX9aB3cD4eF5gH6iJ7kL8mN9oP0q",       # a long random token on its own
])
def test_a_secret_in_a_write_still_asks(text):
    assert hard_floor("add_step", {"task": TASK_ID, "title": text}, STATE) == "secret"
