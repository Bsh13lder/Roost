"""Task views, search and sort — the pure rules (Task 10). Today is fixed: Tue 20 Oct 2026."""

from __future__ import annotations

from datetime import date

from roost.constants import TASK_DONE_VIEW_LIMIT
from roost.tasks.models import Task
from roost.tasks.views import in_view, pick

TODAY = date(2026, 10, 20)


def make(title: str, *, due: str | None = None, status: str = "todo", priority: str = "medium",
         created: str = "2026-10-01T08:00:00+00:00", completed: str | None = None, description: str | None = None) -> Task:
    return Task(
        id=title, user_id="u", title=title, description=description, category=None, priority=priority,  # type: ignore[arg-type]
        status=status, owner="user", due_date=due, reminder_at=None, pre_reminders=(), recurring=None,  # type: ignore[arg-type]
        recur_until=None, tags=(), steps=(), created_at=created, updated_at=created, completed_at=completed,
        created_by_bot=None, tainted=False,
    )


def titles(tasks) -> list[str]:
    return [task.title for task in tasks]


def test_today_has_due_today_and_timed_today():
    tasks = [make("day", due="2026-10-20"), make("timed", due="2026-10-20T09:30:00+02:00"),
             make("yesterday", due="2026-10-19"), make("tomorrow", due="2026-10-21"),
             make("closed", due="2026-10-20", status="done")]
    assert titles(pick(tasks, "today", today=TODAY)) == ["day", "timed"] or set(titles(pick(tasks, "today", today=TODAY))) == {"day", "timed"}


def test_overdue_is_before_today_and_open():
    tasks = [make("late", due="2026-10-19"), make("later", due="2026-10-19T23:00:00+02:00"),
             make("now", due="2026-10-20"), make("none"), make("finished", due="2026-10-01", status="done"),
             make("busy", due="2026-10-10", status="in_progress")]
    assert set(titles(pick(tasks, "overdue", today=TODAY))) == {"late", "later", "busy"}


def test_upcoming_is_after_today():
    tasks = [make("soon", due="2026-10-21"), make("today", due="2026-10-20"), make("none"),
             make("far", due="2027-01-01T10:00:00+01:00"), make("done", due="2026-10-30", status="done")]
    assert set(titles(pick(tasks, "upcoming", today=TODAY))) == {"soon", "far"}


def test_someday_has_no_due():
    tasks = [make("a"), make("b", due="2026-10-21"), make("c", status="done"), make("d", status="cancelled")]
    assert titles(pick(tasks, "someday", today=TODAY)) == ["a"]
    assert in_view(tasks[0], "someday", TODAY) and not in_view(tasks[1], "someday", TODAY)


def test_done_is_newest_first_and_capped():
    tasks = [make(f"t{n:03}", status="done", completed=f"2026-10-{1 + n % 28:02}T{n % 24:02}:00:00+00:00")
             for n in range(TASK_DONE_VIEW_LIMIT + 20)]
    tasks.append(make("failed", status="failed", completed="2026-10-30T00:00:00+00:00"))
    tasks.append(make("open"))
    got = pick(tasks, "done", today=TODAY)
    assert len(got) == TASK_DONE_VIEW_LIMIT
    stamps = [task.completed_at for task in got]
    assert stamps == sorted(stamps, reverse=True)
    assert "failed" not in titles(got) and "open" not in titles(got)


def test_search_is_case_and_accent_insensitive_over_title_and_description():
    tasks = [make("Renovar PASAPORTE"), make("Café con Ana"), make("Other", description="llamar al médico"),
             make("Nothing")]
    assert titles(pick(tasks, "someday", today=TODAY, query="pasaporte")) == ["Renovar PASAPORTE"]
    assert titles(pick(tasks, "someday", today=TODAY, query="CAFE")) == ["Café con Ana"]
    assert titles(pick(tasks, "someday", today=TODAY, query="medico")) == ["Other"]
    assert titles(pick(tasks, "someday", today=TODAY, query="  ")) == titles(tasks)


def test_sort_by_due_then_priority():
    tasks = [make("none-urgent", priority="urgent"), make("b-low", due="2026-10-22", priority="low"),
             make("a-high", due="2026-10-21", priority="high"), make("b-urgent", due="2026-10-22", priority="urgent")]
    assert titles(pick(tasks, None, today=TODAY, sort="due")) == ["a-high", "b-urgent", "b-low", "none-urgent"]
    assert titles(pick(tasks, None, today=TODAY, sort="priority")) == ["b-urgent", "none-urgent", "a-high", "b-low"]
    newer = [make("old", created="2026-10-01T00:00:00+00:00"), make("new", created="2026-10-09T00:00:00+00:00")]
    assert titles(pick(newer, None, today=TODAY, sort="created")) == ["new", "old"]
