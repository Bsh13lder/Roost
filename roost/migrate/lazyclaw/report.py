"""The dry-run report: counts, per-currency numbers, truncated samples, anomalies, the wipe."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal

from roost.migrate.lazyclaw.constants import SAMPLE_TITLE_CHARS, SAMPLES_PER_KIND
from roost.migrate.lazyclaw.models import Anomaly, Mapped

ZERO = Decimal("0.00")


@dataclass(frozen=True)
class WipeCounts:
    """What ``--apply`` would first clear for this user (user decision 2)."""

    available: bool
    tasks: int = 0
    task_comments: int = 0
    expenses: int = 0
    topups: int = 0
    recurring: int = 0
    projects: int = 0   # every project except General


@dataclass(frozen=True)
class ProjectLine:
    name: str
    currency: str
    budget: Decimal | None
    live_topups: Decimal
    spent_lazyclaw: dict[str, Decimal]   # every posted expense, per currency (never added across currencies)
    spent_roost: Decimal      # posted expenses in the project's own currency (Roost's way)
    remaining: Decimal | None


@dataclass(frozen=True)
class CurrencyTotal:
    budget: Decimal = ZERO
    spent_roost: Decimal = ZERO


@dataclass(frozen=True)
class Report:
    counts: dict
    projects: tuple[ProjectLine, ...]
    totals: dict[str, CurrencyTotal]
    samples: dict[str, tuple[str, ...]]
    anomalies: tuple[Anomaly, ...]
    skipped: dict[str, int]
    lost: dict[str, int]
    wipe: WipeCounts
    blocked: bool = field(default=False)


def truncate(value: str | None, limit: int = SAMPLE_TITLE_CHARS) -> str:
    if not value:
        return ""
    return value if len(value) <= limit else value[: limit - 1] + "…"


def _counts(m: Mapped) -> dict:
    statuses = Counter(t.status for t in m.tasks)
    live = [t for t in m.topups if t.deleted_at is None]
    return {
        "tasks_by_status": dict(sorted(statuses.items())),
        "steps": sum(len(t.steps) for t in m.tasks), "comments": len(m.comments),
        "projects_active": sum(p.status == "active" for p in m.projects),
        "projects_archived": sum(p.status == "archived" for p in m.projects),
        "topups_live": len(live), "topups_history": len(m.topups) - len(live),
        "topups_opening": sum(t.opening for t in m.topups),
        "expenses_posted": sum(e.status == "posted" for e in m.expenses),
        "expenses_void": sum(e.status == "void" for e in m.expenses),
        "recurring_active": sum(r.deleted_at is None for r in m.recurring),
        "recurring_paused": sum(r.deleted_at is not None for r in m.recurring),
        "tainted": sum(t.tainted for t in m.tasks),
        "clean": sum(1 for t in m.tasks if not t.tainted),
    }


def _project_lines(m: Mapped) -> tuple[ProjectLine, ...]:
    lines: list[ProjectLine] = []
    for p in m.projects:
        posted = [e for e in m.expenses if e.project_id == p.target_id and e.status == "posted"]
        roost = sum((e.amount for e in posted if e.currency == p.currency), ZERO)
        live = sum((t.amount for t in m.topups if t.project_id == p.target_id and t.deleted_at is None), ZERO)
        by_currency: dict[str, Decimal] = {}
        for e in posted:
            by_currency[e.currency] = by_currency.get(e.currency, ZERO) + e.amount
        lines.append(ProjectLine(
            name=truncate(p.name), currency=p.currency, budget=p.budget, live_topups=live,
            spent_lazyclaw=dict(sorted(by_currency.items())), spent_roost=roost,
            remaining=None if p.budget is None else p.budget - roost,
        ))
    return tuple(lines)


def _totals(lines: tuple[ProjectLine, ...]) -> dict[str, CurrencyTotal]:
    out: dict[str, CurrencyTotal] = {}
    for line in lines:
        old = out.get(line.currency, CurrencyTotal())
        out[line.currency] = CurrencyTotal(old.budget + (line.budget or ZERO), old.spent_roost + line.spent_roost)
    return dict(sorted(out.items()))


def _samples(m: Mapped) -> dict[str, tuple[str, ...]]:
    def first(values: list[str | None]) -> tuple[str, ...]:
        return tuple(truncate(v) for v in values[:SAMPLES_PER_KIND])
    return {
        "tasks": first([t.title for t in m.tasks]), "projects": first([p.name for p in m.projects]),
        "expenses": first([e.description for e in m.expenses]), "top-ups": first([t.source for t in m.topups]),
        "recurring": first([r.description for r in m.recurring]),
    }


def build_report(m: Mapped, wipe: WipeCounts) -> Report:
    lines = _project_lines(m)
    return Report(counts=_counts(m), projects=lines, totals=_totals(lines), samples=_samples(m),
                  anomalies=m.anomalies, skipped=dict(m.skipped), lost=dict(m.lost), wipe=wipe, blocked=m.blocked)


# --- text ---------------------------------------------------------------------------------------

def _num(value: Decimal | None) -> str:
    return "-" if value is None else f"{value:.2f}"


def _counts_text(c: dict) -> list[str]:
    by = ", ".join(f"{k} {v}" for k, v in c["tasks_by_status"].items()) or "none"
    return [
        "WHAT WOULD BE IMPORTED",
        f"  tasks: {sum(c['tasks_by_status'].values())} ({by}); steps {c['steps']}; comments {c['comments']}",
        f"  projects: {c['projects_active']} active, {c['projects_archived']} archived",
        f"  top-ups: {c['topups_live']} live ({c['topups_opening']} opening-budget), {c['topups_history']} history",
        f"  expenses: {c['expenses_posted']} posted, {c['expenses_void']} void",
        f"  recurring: {c['recurring_active']} active, {c['recurring_paused']} paused",
        f"  trust: {c['tainted']} marked tainted, {c['clean']} clean tasks (imported rows are trusted)",
    ]


def _per_currency(values: dict[str, Decimal]) -> str:
    return ", ".join(f"{cur} {_num(v)}" for cur, v in values.items()) or "-"


def _money_text(r: Report) -> list[str]:
    out = ["MONEY BY PROJECT (never added across currencies)",
           "  project | cur | budget | live top-ups | spent LazyClaw way | spent Roost way | remaining"]
    out += [f"  {p.name} | {p.currency} | {_num(p.budget)} | {_num(p.live_topups)} | {_per_currency(p.spent_lazyclaw)} | "
            f"{_num(p.spent_roost)} | {_num(p.remaining)}" for p in r.projects]
    out += [f"  total {cur}: budget {_num(t.budget)}, spent {_num(t.spent_roost)}" for cur, t in r.totals.items()]
    return out


def _wipe_text(w: WipeCounts) -> list[str]:
    head = "WIPE BEFORE IMPORT (only with --apply --wipe, and only once ever per account)"
    if not w.available:
        return [head, "  Roost's current rows could not be counted (no Roost database given or readable)."]
    return [head, f"  {w.tasks} tasks, {w.task_comments} task comments, {w.expenses} expenses, {w.topups} top-ups, "
            f"{w.recurring} recurring rules, {w.projects} projects (General is kept).",
            "  Notes and documents are left alone."]


def render_report(r: Report) -> str:
    out = ["LAZYCLAW -> ROOST DRY RUN (nothing was written to Roost)", ""]
    out += _counts_text(r.counts) + [""] + _money_text(r) + [""]
    out += ["SKIPPED / LOST"] + [f"  skipped {k}: {v}" for k, v in sorted(r.skipped.items())]
    out += [f"  lost {k}: {v}" for k, v in sorted(r.lost.items())] + [""]
    out += ["SAMPLES (first 5, cut to 24 characters)"] + [f"  {k}: {' | '.join(v) or '-'}" for k, v in r.samples.items()]
    out += [""] + _wipe_text(r.wipe) + [""]
    out += [f"ANOMALIES ({len(r.anomalies)})"] + [
        f"  [{'STOP' if a.blocking else 'note'}] {a.kind} {a.ref}: {a.detail}" for a in r.anomalies]
    out += ["", "BLOCKED: the anomalies marked STOP must be fixed before --apply." if r.blocked
            else "No blocking anomalies. --apply may run after you have read this."]
    return "\n".join(out)
