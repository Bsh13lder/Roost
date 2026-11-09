// @vitest-environment node
import { readdirSync, readFileSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

// The main bundle stays within bundle-budget.json (redesign P1): the calendar (react-day-picker and
// date-fns) loads only when a calendar opens. A static import anywhere would pull it into the entry.
const SRC = fileURLToPath(new URL("../src/", import.meta.url));
const CALENDAR = "ui/date/Calendar.tsx";
// Redesign P2: react-markdown and remark-gfm live only in the markdown renderer, a lazy chunk the notes
// preview and the chat share.
const MARKDOWN = "components/markdown/Markdown.tsx";
const NOTE_PREVIEW = "components/notes/NotePreview.tsx";
const STATIC_IMPORT = /^\s*import\s[^;]*?from\s+["']([^"']+)["']/gm;
const BARE_IMPORT = /^\s*import\s+["']([^"']+)["']/gm;

function sources(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return sources(path);
    return /\.(ts|tsx)$/.test(entry.name) ? [path] : [];
  });
}

// Every import of `name` in the file is "import type …": erased at build, so not a static import of the code.
function onlyTypeImports(path: string, name: string): boolean {
  const text = readFileSync(path, "utf8");
  const lines = [...text.matchAll(STATIC_IMPORT)].filter((match) => new RegExp(`(^|/)${name}$`).test(match[1]));
  return lines.length > 0 && lines.every((match) => /^\s*import\s+type\s/.test(match[0]));
}

function staticImports(path: string): string[] {
  const text = readFileSync(path, "utf8");
  return [...text.matchAll(STATIC_IMPORT), ...text.matchAll(BARE_IMPORT)].map((match) => match[1]);
}

describe("bundle guard (redesign P1)", () => {
  it("imports react-day-picker only in the lazy calendar chunk", () => {
    const importers = sources(SRC)
      .filter((path) => staticImports(path).some((spec) => spec === "react-day-picker" || spec.startsWith("react-day-picker/")))
      .map((path) => relative(SRC, path));
    expect(importers).toEqual([CALENDAR]);
  });

  it("nothing imports the calendar statically: it is reached through React.lazy only", () => {
    const importers = sources(SRC)
      .filter((path) => staticImports(path).some((spec) => /(^|\/)Calendar$/.test(spec)))
      .map((path) => relative(SRC, path));
    expect(importers).toEqual([]);
    const popover = readFileSync(join(SRC, "ui/date/CalendarPopover.tsx"), "utf8");
    expect(popover).toContain('lazy(() => import("./Calendar"))');
  });

  it("imports react-markdown and remark-gfm only in the markdown renderer", () => {
    const importers = sources(SRC)
      .filter((path) => staticImports(path).some((spec) => spec === "react-markdown" || spec === "remark-gfm"))
      .map((path) => relative(SRC, path));
    expect(importers).toEqual([MARKDOWN]);
  });

  it("reaches the markdown renderer statically only from the notes preview, inside the lazy notes chunk", () => {
    const importers = sources(SRC)
      .filter((path) => staticImports(path).some((spec) => /(^|\/)Markdown$/.test(spec)))
      .map((path) => relative(SRC, path));
    expect(importers).toEqual([NOTE_PREVIEW]);
    const notesBoard = sources(SRC)
      .filter((path) => staticImports(path).some((spec) => /(^|\/)NotesBoard$/.test(spec)))
      .map((path) => relative(SRC, path));
    expect(notesBoard).toEqual([]);
  });

  // Redesign P3: the task drawer, and everything only it uses, is its own chunk.
  it("nothing imports the task drawer statically: the tasks board reaches it through React.lazy only", () => {
    const importers = sources(SRC)
      .filter((path) => staticImports(path).some((spec) => /(^|\/)TaskDrawer$/.test(spec)))
      .map((path) => relative(SRC, path));
    expect(importers).toEqual([]);
    const board = readFileSync(join(SRC, "components/board/TasksBoard.tsx"), "utf8");
    expect(board).toContain('lazy(() => import("../tasks/TaskDrawer"))');
  });

  // Board G6: the Kanban board and its pieces are their own chunk.
  it("Kanban is reached through React.lazy only", () => {
    const importers = sources(SRC)
      .filter((path) => staticImports(path).some((spec) => /(^|\/)KanbanBoard$/.test(spec)))
      .map((path) => relative(SRC, path));
    expect(importers).toEqual([]);
    const board = readFileSync(join(SRC, "components/board/TasksBoard.tsx"), "utf8");
    expect(board).toContain('lazy(() => import("./kanban/KanbanBoard"))');
  });

  // Board G11: the task calendar and the grid it shares with the money calendar are their own chunk.
  it("the task calendar is reached through React.lazy only", () => {
    const importers = sources(SRC)
      .filter((path) => staticImports(path).some((spec) => /(^|\/)TaskCalendar$/.test(spec)))
      .map((path) => relative(SRC, path));
    expect(importers).toEqual([]);
    const board = readFileSync(join(SRC, "components/board/TasksBoard.tsx"), "utf8");
    expect(board).toContain('lazy(() => import("./calendar/TaskCalendar"))');
  });

  // Board G12: the money calendar is a lazy chunk too.
  it("the money calendar is reached through React.lazy only", () => {
    const importers = sources(SRC)
      .filter((path) => staticImports(path).some((spec) => /(^|\/)ExpenseCalendar$/.test(spec)))
      .map((path) => relative(SRC, path));
    expect(importers).toEqual([]);
    const board = readFileSync(join(SRC, "components/board/MoneyBoard.tsx"), "utf8");
    expect(board).toContain('lazy(() => import("./calendar/ExpenseCalendar"))');
  });

  // Final-review fix: the chat preloads the chunk when it opens; the preload and React.lazy share one
  // dynamic import, so the renderer still stays out of the entry.
  it("the chat reaches the markdown renderer through a dynamic import only, shared by React.lazy and the preload", () => {
    const richText = readFileSync(join(SRC, "components/chat/RichText.tsx"), "utf8");
    // One import() that loads code; "typeof import(…)" is only a type and is erased.
    expect(richText.match(/(?<!typeof )import\("[^"]+"\)/g)).toEqual(['import("../markdown/Markdown")']);
    expect(richText).toContain("lazy(loadMarkdown)");
    expect(richText).toMatch(/async function preloadMarkdown\(\)[\s\S]*?await loadMarkdown\(\)/);
  });

  // Routines plan: the Plan tab (calendar, kanban, text editor) and the routines card are lazy chunks.
  it("the Plan view is reached through React.lazy only", () => {
    const importers = sources(SRC)
      .filter((path) => staticImports(path).some((spec) => /(^|\/)PlanView$/.test(spec)))
      .map((path) => relative(SRC, path));
    expect(importers).toEqual([]);
    const tab = readFileSync(join(SRC, "components/plan/PlanTab.tsx"), "utf8");
    expect(tab).toContain('lazy(() => import("./PlanView"))');
  });

  it("the routines section is reached through React.lazy only", () => {
    const importers = sources(SRC)
      .filter((path) => staticImports(path).some((spec) => /(^|\/)RoutinesSection$/.test(spec)))
      .map((path) => relative(SRC, path));
    expect(importers).toEqual([]);
    const plan = readFileSync(join(SRC, "components/plan/PlanRoutinesPage.tsx"), "utf8");
    expect(plan).toContain('lazy(() => import("../routines/RoutinesSection"))');
  });

  it("the run log page is reached through React.lazy only", () => {
    const importers = sources(SRC)
      .filter((path) => staticImports(path).some((spec) => /(^|\/)RoutineLog$/.test(spec)))
      .map((path) => relative(SRC, path));
    expect(importers).toEqual([]);
  });

  // Lead task 03: the Board, Project, NewBot, Room and Instructions pages are route-level chunks.
  it("the big pages are reached through React.lazy only, from the routes", () => {
    for (const page of ["Board", "Project", "NewBot", "Room", "Instructions"]) {
      const importers = sources(SRC)
        .filter((path) => staticImports(path).some((spec) => spec === `./pages/${page}` || spec.endsWith(`pages/${page}`) || spec === `./${page}`))
        .map((path) => relative(SRC, path));
      expect(importers, page).toEqual([]);
      const app = readFileSync(join(SRC, "App.tsx"), "utf8");
      expect(app, page).toContain(`import("./pages/${page}")`);
    }
  });

  // Lead task 12: the bot's profile panel (its tabs, and what only they use) is its own chunk. A type-only import is
  // erased, so it does not count.
  it("the bot's profile panel is reached through React.lazy only, shared with the pill's preload", () => {
    const importers = sources(SRC)
      .filter((path) => staticImports(path).some((spec) => /(^|\/)BotPanel$/.test(spec)) && !onlyTypeImports(path, "BotPanel"))
      .map((path) => relative(SRC, path));
    expect(importers).toEqual([]);
    const lazyPanel = readFileSync(join(SRC, "components/panel/lazyBotPanel.tsx"), "utf8");
    expect(lazyPanel.match(/(?<!typeof )import\("[^"]+"\)/g)).toEqual(['import("./BotPanel")']);
    expect(lazyPanel).toContain("lazy(() => loadBotPanel()");
    const chat = readFileSync(join(SRC, "pages/Chat.tsx"), "utf8");
    expect(chat).toContain("LazyBotPanel");
    expect(chat).toContain("preloadBotPanel");
  });
});

describe("bundle guard (Skills)", () => {
  it("the Skills section, card and import sheet are reached through React.lazy only", () => {
    const importers = sources(SRC)
      .filter((path) => !relative(SRC, path).startsWith("components/skills/"))
      .filter((path) => staticImports(path).some((spec) => /(^|\/)(SkillsSection|SkillEditor|SkillAskCard|TemplateSkillsSheet)$/.test(spec)))
      .map((path) => relative(SRC, path));
    expect(importers).toEqual([]);
    const settings = readFileSync(join(SRC, "components/profile/SettingsPage.tsx"), "utf8");
    expect(settings).toContain('lazy(() => import("../skills/SkillsSection"))');
  });
});
