# SPDX-License-Identifier: MIT
# Harvested from LazyClaw lazyclaw/skills/builtin/task_manager.py lines 49-50, 75-110, 157-182 @ 21e1002, adapted for Roost

"""Rendering a task for a tool result or the Board (M1 D6): the harvested
relative/local time format, plus Roost's typed task line and HTTP shape."""

from __future__ import annotations

import html
from datetime import datetime, timezone
from typing import Any

from roost.money.amounts import amount_text
from roost.records.paging import more_line
from roost.timezones import local_tz, zone_city
from roost.tasks.models import Task
from roost.tasks.repeat_words import readable

_PRIORITY_ICON = {"urgent": "!!", "high": "!", "medium": "-", "low": "."}
_STATUS_ICON = {"todo": "[ ]", "in_progress": "[~]", "done": "[x]", "cancelled": "[-]", "failed": "[✗]"}


def format_time(iso_str: str, now: datetime | None = None) -> str:
    """Format an ISO datetime as relative + local absolute time."""
    if not iso_str or len(iso_str) < 10:
        return iso_str
    try:
        dt = datetime.fromisoformat(iso_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        now = now or datetime.now(timezone.utc)
        local_dt = dt.astimezone(local_tz())
        local_time = local_dt.strftime("%H:%M")
        diff = dt - now

        if diff.total_seconds() < 0:
            ago = abs(diff.total_seconds())
            if ago < 3600:
                return f"{int(ago // 60)}m ago ({local_time})"
            return f"{int(ago // 3600)}h ago ({local_time})"
        elif diff.total_seconds() < 3600:
            return f"in {int(diff.total_seconds() // 60)}m ({local_time})"
        elif diff.total_seconds() < 86400:
            h = int(diff.total_seconds() // 3600)
            m = int((diff.total_seconds() % 3600) // 60)
            return f"in {h}h {m}m ({local_time})"
        else:
            return f"in {diff.days}d ({local_dt.strftime('%b %d %H:%M')})"
    except (ValueError, TypeError):
        return iso_str[:16]


def _escape(text: str) -> str:
    """Tool results reach the model unescaped (claude_sdk renders them raw):
    user and page text is escaped here, by its producer."""
    return html.escape(text, quote=True)


def task_line(task: Task, now: datetime | None = None) -> str:
    parts = [_STATUS_ICON.get(task.status, "[ ]"), f"{_PRIORITY_ICON.get(task.priority, '-')} {_escape(task.title)}"]
    if task.reminder_at:
        parts.append(f"({format_time(task.reminder_at, now)})")
    elif task.due_date:
        parts.append(f"(due {task.due_date})")
    if task.category:
        parts.append(f"[{_escape(task.category)}]")
    if task.recurring:
        parts.append("[repeats]")
    if task.tainted:
        parts.append("[from web content]")
    parts.append(f"id={task.id}")
    return " ".join(parts)


def _local(iso_str: str) -> str:
    try:
        dt = datetime.fromisoformat(iso_str)
    except (ValueError, TypeError):
        return iso_str[:16]
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(local_tz()).strftime("%b %d %H:%M")


def reminders_text(task: Task) -> str:
    """Every reminder the task will send, earliest first, so a bot never thinks one is missing; "" when none."""
    if not task.reminder_at:
        return ""
    before = ", ".join(_local(at) for at in sorted(task.pre_reminders))
    lead = f"{before}, and at " if before else "at "
    return f" Reminders ({zone_city()}): {lead}{_local(task.reminder_at)}."


def task_list_text(tasks: tuple[Task, ...], total: int, offset: int = 0) -> str:
    if not tasks:
        return "No tasks match." if total == 0 else f"Nothing more: all {total} tasks are listed."
    return "\n".join(task_line(task) for task in tasks) + more_line(total, offset, len(tasks))


def task_out(task: Task) -> dict[str, Any]:
    return {
        "id": task.id, "title": task.title, "description": task.description, "category": task.category,
        "priority": task.priority, "status": task.status, "owner": task.owner, "due_date": task.due_date,
        "reminder_at": task.reminder_at, "pre_reminders": list(task.pre_reminders), "recurring": task.recurring,
        "recur_until": task.recur_until, "tags": list(task.tags),
        "steps": [{"id": s.id, "title": s.title, "done": s.done} for s in task.steps],
        "created_at": task.created_at, "updated_at": task.updated_at, "completed_at": task.completed_at,
        "created_by_bot": task.created_by_bot, "tainted": task.tainted, "project_id": task.project_id,
        # The server sends every amount as a string; the web never adds them.
        "allocated_budget": None if task.allocated_budget is None else amount_text(task.allocated_budget),
        "starred": task.starred, "estimate_minutes": task.estimate_minutes,
        "repeat_text": None if not task.recurring else readable(task.recurring),
        "imported_from": task.imported_from,
    }

