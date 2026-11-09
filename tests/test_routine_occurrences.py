"""Routine run times on the calendars: the pure occurrences module (Madrid days, caps, paused routines)."""

from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from roost.routines.models import Routine
from roost.routines.occurrences import madrid_span, occurrences_between
from roost.routines.schedule import parse_schedule

MADRID = ZoneInfo("Europe/Madrid")
UTC = timezone.utc
ALL_DAYS = [1, 2, 3, 4, 5, 6, 7]
CREATED = datetime(2026, 10, 1, tzinfo=UTC)


def madrid(y, mo, d, h=0, mi=0) -> datetime:
    return datetime(y, mo, d, h, mi, tzinfo=MADRID).astimezone(UTC)


def routine(rid: str, schedule: dict, *, bot_id: str = "b1", enabled: bool = True, name: str = "Morning") -> Routine:
    return Routine(
        id=rid, user_id="u1", bot_id=bot_id, thread_id=f"t-{rid}", name=name, instructions="Do it.",
        schedule=parse_schedule(schedule), builtin=None, enabled=enabled, tainted=False, created_by="user",
        next_run_at=None, last_run_at=None, created_at=CREATED, updated_at=CREATED)


def daily(*hhmm: str) -> dict:
    return {"kind": "times", "days": ALL_DAYS, "times": list(hhmm)}


def test_madrid_span_covers_whole_madrid_days():
    start, end = madrid_span(date(2026, 10, 24), date(2026, 10, 25))
    assert start == madrid(2026, 10, 24) and end == madrid(2026, 10, 26)  # the 25th is 25 hours long (DST ends)


def test_occurrences_are_madrid_times_with_names_oldest_first():
    found = occurrences_between(
        (routine("r1", daily("09:00"), name="News"), routine("r2", daily("08:30"), bot_id="b2", name="Gym")),
        {"b1": "Gela", "b2": "Max"}, madrid(2026, 10, 27), madrid(2026, 10, 29), cap=50)
    assert [(o.routine_name, o.bot_name, o.at.astimezone(MADRID).strftime("%d %H:%M")) for o in found.occurrences] == [
        ("Gym", "Max", "27 08:30"), ("News", "Gela", "27 09:00"), ("Gym", "Max", "28 08:30"), ("News", "Gela", "28 09:00")]
    assert found.truncated is False
    first = found.occurrences[0]
    assert (first.routine_id, first.bot_id, first.thread_id) == ("r2", "b2", "t-r2")
    assert first.day == "2026-10-27" and first.time == "08:30" and first.at.tzinfo == UTC


def test_a_fire_at_midnight_counts_on_its_own_day_and_the_end_is_exclusive():
    found = occurrences_between((routine("r1", daily("00:00")),), {"b1": "Gela"},
                                madrid(2026, 10, 27), madrid(2026, 10, 28), cap=50)
    assert [o.day for o in found.occurrences] == ["2026-10-27"]


def test_paused_routines_are_left_out():
    found = occurrences_between((routine("r1", daily("09:00"), enabled=False),), {"b1": "Gela"},
                                madrid(2026, 10, 27), madrid(2026, 10, 28), cap=50)
    assert found.occurrences == ()


def test_watching_routines_are_left_out():
    from dataclasses import replace

    from roost.routines.watch_models import Watch

    watching = replace(routine("r1", daily("09:00")), watch=Watch(url="https://shop.example/", part="", every_min=5))
    found = occurrences_between((watching,), {"b1": "Gela"}, madrid(2026, 10, 27), madrid(2026, 10, 28), cap=50)
    assert found.occurrences == ()


def test_a_routine_of_a_bot_with_no_name_reads_empty():
    found = occurrences_between((routine("r1", daily("09:00")),), {}, madrid(2026, 10, 27), madrid(2026, 10, 28), cap=5)
    assert found.occurrences[0].bot_name == ""


def test_the_cap_keeps_the_earliest_and_says_it_cut():
    every_15 = {"kind": "cron", "expr": "*/15 * * * *"}
    found = occurrences_between((routine("r1", every_15), routine("r2", daily("00:05"))), {"b1": "Gela"},
                                madrid(2026, 10, 27), madrid(2026, 11, 3), cap=10)
    assert len(found.occurrences) == 10 and found.truncated is True
    assert [o.time for o in found.occurrences[:3]] == ["00:00", "00:05", "00:15"]


def test_cron_and_times_both_fill_a_week():
    weekdays = {"kind": "times", "days": [1, 2, 3, 4, 5], "times": ["10:07"]}
    found = occurrences_between((routine("r1", weekdays),), {"b1": "Gela"},
                                madrid(2026, 10, 26), madrid(2026, 11, 2), cap=50)
    assert [o.day for o in found.occurrences] == ["2026-10-26", "2026-10-27", "2026-10-28", "2026-10-29", "2026-10-30"]


def test_an_empty_window_gives_nothing():
    found = occurrences_between((routine("r1", daily("09:00")),), {"b1": "Gela"},
                                madrid(2026, 10, 28), madrid(2026, 10, 27), cap=50)
    assert found.occurrences == () and found.truncated is False
