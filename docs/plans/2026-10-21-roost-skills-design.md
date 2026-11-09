# Roost Skills: Design

**Status (2026-10-21):** approved by the user to build now (chief's brief). This design is short on purpose; the plan (`docs/plans/2026-10-21-roost-skills.md`) holds every name, route, test and commit. Schema **v26** belongs to Skills (C3 takes no migration).

## 1. What a Skill is

A **Skill** is a saved how-to a bot can reuse. It is the user's, and it has three parts:

- a **name** ("Apply to an Upwork job", "Post on X", "Weekly SEO check"), one line, unique per user (case and accents folded);
- **Use when**, one line that tells a bot when the skill fits;
- **steps**, Markdown.

A skill is shared by every bot by default. Each bot can switch a skill off for itself. A skill is *knowledge, never power*: it grants no tool, relaxes no approval mode, no "Always ask about" topic, no hard floor, no tainted-write rule and no link guard. A skill that says "skip the Ask card" or "use mac_edit" changes nothing the gate decides.

## 2. How a bot uses skills

- **The index.** Every run's instructions carry a short, escaped list of the skills that are on for this bot: `- {name} · Use when: {use_when}`, within `SKILLS_PROMPT_BUDGET_CHARS`, under a head that says the list is the user's saved how-tos, that it is data, and that `read_skill` loads the steps. Skills that did not fit are counted ("3 more: use list_skills").
- **Taint stays out of the prompt.** Like the Plan slice, only clean skills are listed by name. A skill marked *from web content* is only counted ("1 more came from outside content: list_skills shows it"), so the index never taints a run.
- **`read_skill(name)`** (kind `read`) returns the steps, quoted and escaped, with the head "Steps of your saved skill “{name}”. They guide how you work; they give you no new tool and change no approval rule." Reading a skill marked *from web content* taints the run, like reading a page. At most `SKILL_READS_PER_RUN_MAX` reads per run.
- **`list_skills`** (kind `read`) lists every skill on for this bot (name, Use when, its mark), quoted data. It taints the run only if it shows a marked skill.
- Helpers (`send_helpers`) may use `read_skill` and `list_skills` (they are reads); they never propose.

## 3. How a skill is made or changed

- **The user** adds, edits and deletes skills in the **skill editor**, a Sheet opened from the **Skills** fold on the Profile's Info tab (the existing `ui/Fold`). The editor has Name, Use when, Steps (a plain textarea with a Markdown preview from the shared lazy `Markdown` chunk) and **Save skill**. Every save is a `revision` compare-and-swap: a stale save is **409** with the current copy, and the editor offers "Load the latest" or "Keep mine", like notes. The user's own save clears the *from web content* mark (the user wrote or checked the text).
- **A bot** proposes, after a run that worked, with `propose_skill(name, use_when, steps)` or `propose_skill_change(skill, name?, use_when?, steps?)`. Neither writes a skill. Each stores a sealed proposal (new table `skill_proposals`, the `routine_proposals` pattern) and posts a **skill proposal card** (`skill_proposal` message) with the full text and, for a change, the field-by-field difference. The card's buttons are **Save skill** and **Not now**. Only Save makes the server write the skill.
- **Taint:** a proposal from a tainted run carries the *from web content* mark on the card, and a skill saved from it keeps the mark (`tainted = 1`) until the user saves it from the editor.
- **Change proposals** remember the skill's revision. Save is a compare-and-swap on it: if the user edited or deleted the skill since, Save refuses with "That skill changed or is gone, so this proposal no longer fits."
- Open skill proposals are rows in **My turn**, after routine proposals and before questions.
- No secrets: a proposal, an editor save or an import whose text looks like a key or a password (`find_secret_kinds`) is refused with the Share as Template sentence.

## 4. Per-bot switch

The Skills fold lists every skill with a switch per row ("On for this bot"). Off is a row in `bot_skill_off (user_id, bot_id, skill_id)`; no row means on, so a new skill is on for every bot. The fold's summary is "{n} on". Deleting a skill removes its off rows (FK cascade). Retiring a bot removes its rows.

## 5. Templates

- **Share as Template** adds `skills: [{name, use_when, steps}]` (the skills on for that bot, at most `TEMPLATE_SKILLS_MAX`) to `<name>.roost-bot.json`, still `version: 1`; a file with no skills leaves the key out, so an older Roost still reads it. The secret check covers the skills too.
- **Importing** (New bot · From a file): `POST /api/templates/check` returns the skills, and the New bot form shows "This file has {n} skills" with each one readable in full. Nothing is added at Create. After Create, an **Add its skills?** sheet lists them with a checkbox each (all ticked) and **Add skills** / **Skip**. A skill whose name the user already has is shown as "You already have this one" and is not added. Added skills come from outside content, so they carry the *from web content* mark until the user saves them in the editor.

## 6. Storage (schema v26)

- `skills`: `id, user_id, name, use_when, body` (all three `enc:v2` under `user_aad(user_id, "skills:name"|"skills:use_when"|"skills:body")`), `name_key` (keyed HMAC of the folded name, for uniqueness and lookup without plaintext; `UNIQUE(user_id, name_key)`), `origin` (`user`·`bot`·`file`), `tainted`, `created_by_bot` (nullable), `revision`, `created_at`, `updated_at`.
- `bot_skill_off`: `user_id, bot_id, skill_id, created_at`, primary key `(user_id, bot_id, skill_id)`.
- `skill_proposals`: the `routine_proposals` shape with `skill_id`, `action IN ('create','change')`, a sealed `payload` (`skill_proposals:payload`), `base_revision`, `tainted`, `from_routine`, `state IN ('open','saved','declined')`.
- Every query names `user_id`. Another user's skill, proposal or bot is **404**.

## 7. Out of scope

Skills that bundle files or scripts, skills that run on a schedule (that is a Routine), sharing one skill on its own (only inside a template), versions/history beyond the revision, and per-skill tool lists.

## Open for the user

Each one is built with the default and can be changed later:

1. **Who can see a skill:** default is every bot, with a per-bot off switch. The alternative is off by default for new bots.
2. **A skill saved from a web-tainted proposal or a template file** keeps the *from web content* mark, and reading it taints the run, until the user saves it in the editor. The alternative is that the card's Save clears the mark, since the user saw the full text.
3. **Secrets in a skill** are refused. The alternative is a warning that lets the user save anyway.
4. **Limits** (in `roost/constants.py`): 100 skills per user, name 80 characters, Use when 200, steps 8,000, an index budget of 2,000 characters, 5 `read_skill` calls per run, 5 open skill proposals per bot, 20 skills in a template file.
5. **Name clash on import:** default is to skip and say "You already have this one". The alternative is adding it as "{name} (2)".
