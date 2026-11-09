"""What the export writes, pure: a project, its tasks, notes and money, and the bots' journal days, as
Obsidian Markdown files with front matter tags and ``[[wikilinks]]`` between project, task and note.

    Roost/Projects/<Project>/<Project>.md        the project: its numbers and links to everything below
    Roost/Projects/<Project>/Tasks/<Task>.md     one per task, with its steps as a checklist
    Roost/Projects/<Project>/Notes/<Note>.md     one per note, its own Markdown under Roost's front matter
    Roost/Projects/<Project>/<Project> · Money.md  the project's expenses and money in, as a table
    Roost/Journals/<Bot>/<YYYY-MM-DD>.md         a bot's journal day, as Roost keeps it

Web-made records say so (``from_web: true``), and their text is defanged (``defang.py``): no remote image,
embed, link, HTML or code fence from a web page reaches the vault live. A title stays on one line and inside
its wikilink or heading."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from roost.constants import VAULT_EXPORT_ROOT
from roost.journal.models import JournalDay
from roost.money.amounts import amount_text
from roost.money.models import Expense, Project
from roost.notes.frontmatter import parse_frontmatter
from roost.notes.models import Note
from roost.tags.rules import project_tag
from roost.tasks.models import Task
from roost.vault_export.defang import body as own_text
from roost.vault_export.defang import heading, markdown_body
from roost.vault_export.names import file_name, unique_names
from roost.vault_export.yaml import front_matter, link, vault_tags

_DONE = frozenset({"done"})
_OUR_KEYS = frozenset({"roost_id", "type", "tags", "project", "from_web"})


@dataclass(frozen=True)
class ExportFile:
    path: str      # relative to the grant's folder
    text: str


@dataclass(frozen=True)
class ProjectBundle:
    project: Project
    tasks: tuple[Task, ...]
    notes: tuple[Note, ...]
    expenses: tuple[Expense, ...]


@dataclass(frozen=True)
class _Folder:
    base: str
    name: str
    project_path: str
    task_paths: Mapping[str, str]
    note_paths: Mapping[str, str]

    @property
    def money_path(self) -> str:
        return f"{self.base}/{self.name} · Money.md"


def _folder(bundle: ProjectBundle, name: str) -> _Folder:
    base = f"{VAULT_EXPORT_ROOT}/Projects/{name}"
    tasks = unique_names((t.id, t.title) for t in sorted(bundle.tasks, key=lambda t: (t.created_at, t.id)))
    notes = unique_names((n.id, n.title) for n in sorted(bundle.notes, key=lambda n: (n.created_at, n.id)))
    return _Folder(base, name, f"{base}/{name}.md", {k: f"{base}/Tasks/{v}.md" for k, v in tasks.items()},
                   {k: f"{base}/Notes/{v}.md" for k, v in notes.items()})


def _project_file(bundle: ProjectBundle, folder: _Folder) -> ExportFile:
    p = bundle.project
    head = front_matter((
        ("roost_id", p.id), ("type", "project"), ("status", p.status), ("currency", p.currency),
        ("budget", amount_text(p.budget) if p.budget is not None else None),
        ("monthly_budget", amount_text(p.monthly_budget) if p.monthly_budget is not None else None),
        ("start", p.start_date), ("due", p.due_date), ("tags", vault_tags("roost/project", (project_tag(p.name),))),
        ("from_web", True if p.tainted else None)))
    tasks = [f"- [{'x' if t.status in _DONE else ' '}] {link(folder.task_paths[t.id], t.title)}"
             + (f" 📅 {t.due_date[:10]}" if t.due_date else "") for t in bundle.tasks]
    notes = [f"- {link(folder.note_paths[n.id], n.title)}" for n in bundle.notes]
    body = [f"# {heading(p.name)}", "", "## Tasks", *(tasks or ["- (none)"]), "", "## Notes", *(notes or ["- (none)"]),
            "", "## Money", f"- {link(folder.money_path, 'Money')}"]
    return ExportFile(folder.project_path, head + "\n".join(body) + "\n")


def _task_file(task: Task, project: Project, folder: _Folder) -> ExportFile:
    head = front_matter((
        ("roost_id", task.id), ("type", "task"), ("status", task.status), ("priority", task.priority),
        ("due", task.due_date), ("completed", task.completed_at), ("project", link(folder.project_path, project.name)),
        ("tags", vault_tags("roost/task", task.tags)), ("from_web", True if task.tainted else None)))
    steps = [f"- [{'x' if s.done else ' '}] {own_text(s.title, task.tainted)}" for s in task.steps]
    body = [f"# {heading(task.title)}", ""]
    if task.description:
        body += [own_text(task.description.strip(), task.tainted), ""]
    if steps:
        body += ["## Steps", *steps, ""]
    body.append(f"Project: {link(folder.project_path, project.name)}")
    return ExportFile(folder.task_paths[task.id], head + "\n".join(body) + "\n")


def _note_file(note: Note, project: Project, folder: _Folder) -> ExportFile:
    props, body, _has = parse_frontmatter(note.content)
    theirs = [(key, value) for key, value in props.items() if key not in _OUR_KEYS]
    head = front_matter((
        ("roost_id", note.id), ("type", "note"), ("project", link(folder.project_path, project.name)),
        ("tags", vault_tags("roost/note", note.tags)), ("from_web", True if note.tainted else None), *theirs))
    tail = f"\n\nProject: {link(folder.project_path, project.name)}\n"
    text = own_text(body.rstrip("\n"), note.tainted)
    return ExportFile(folder.note_paths[note.id], head + text + tail)


def _money_file(bundle: ProjectBundle, folder: _Folder) -> ExportFile:
    p = bundle.project
    head = front_matter((("roost_id", p.id), ("type", "money"), ("currency", p.currency),
                         ("project", link(folder.project_path, p.name)), ("tags", vault_tags("roost/money", ()))))
    rows = [f"| {e.spent_at} | {_cell(e.description, e.tainted)} | {_cell(e.vendor, e.tainted)} | {'+' if e.kind == 'income' else ''}"
            f"{amount_text(e.amount)} {e.currency} | {e.status} | {_tag_cell(e.tags)} |"
            for e in sorted(bundle.expenses, key=lambda e: (e.spent_at, e.created_at, e.id))]
    table = ["| Day | What | Vendor | Amount | Status | Tags |", "| --- | --- | --- | --- | --- | --- |", *rows]
    body = [f"# {heading(p.name)} · Money", "", *(table if rows else ["No expenses yet."]), "",
            f"Project: {link(folder.project_path, p.name)}"]
    return ExportFile(folder.money_path, head + "\n".join(body) + "\n")


def _tag_cell(tags: tuple[str, ...]) -> str:
    return " ".join(f"#{tag}" for tag in vault_tags("roost/expense", tags)[1:])


def _cell(text: str | None, tainted: bool) -> str:
    return own_text((text or "").replace("|", "/").replace("\n", " ").strip(), tainted)


def project_files(bundles: Iterable[ProjectBundle]) -> tuple[ExportFile, ...]:
    ordered = sorted(bundles, key=lambda b: (b.project.created_at, b.project.id))
    names = unique_names((b.project.id, b.project.name) for b in ordered)
    files: list[ExportFile] = []
    for bundle in ordered:
        folder = _folder(bundle, names[bundle.project.id])
        files += [_project_file(bundle, folder), _money_file(bundle, folder)]
        files += [_task_file(t, bundle.project, folder) for t in bundle.tasks]
        files += [_note_file(n, bundle.project, folder) for n in bundle.notes]
    return tuple(files)


def journal_files(days: Iterable[JournalDay], bot_names: Mapping[str, str]) -> tuple[ExportFile, ...]:
    """A bot's day as Roost keeps it (already Obsidian Markdown), under the bot's own folder; a day a web
    page touched is defanged below its front matter."""
    listed = tuple(days)
    folders = unique_names((bot_id, bot_names.get(bot_id, "Retired bot"))
                           for bot_id in dict.fromkeys(sorted(d.bot_id for d in listed)))
    return tuple(ExportFile(f"{VAULT_EXPORT_ROOT}/Journals/{folders[d.bot_id]}/{d.day.isoformat()}.md",
                                    markdown_body(d.content, d.tainted))
                 for d in listed)


__all__ = ["ExportFile", "ProjectBundle", "file_name", "journal_files", "project_files"]
