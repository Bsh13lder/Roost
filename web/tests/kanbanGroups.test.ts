import { describe, expect, it } from "vitest";
import {
  columnOf, columnsFor, KANBAN_GROUPS, KANBAN_SORTS, moveFor, visibleTasks, type KanbanContext,
} from "../src/components/board/kanban/kanbanGroups";
import { makeRow } from "./taskFixtures";

const TODAY = "2026-10-20";
const CTX: KanbanContext = {
  tasks: [],
  projects: [{ id: "p1", name: "Casa Nueva", color: "#22c55e" }, { id: "p2", name: "Lisbon", color: "#3b82f6" }],
  bots: { b1: { name: "Chief" }, b2: { name: "Scout" } },
};
const keys = (group: Parameters<typeof columnsFor>[0], ctx: KanbanContext = CTX) => columnsFor(group, ctx).map((c) => c.key);

describe("kanbanGroups", () => {
  it("offers the six groupings and the six sorts", () => {
    expect(KANBAN_GROUPS.map((g) => g.label)).toEqual(["Status", "Due date", "Project", "Priority", "Bot", "List"]);
    expect(KANBAN_SORTS.map((s) => s.value)).toEqual(["due", "priority", "created", "created_asc", "title", "money_left"]);
    expect(KANBAN_SORTS.map((s) => s.label)).toEqual(["Due date", "Priority", "Newest", "Oldest", "Title A–Z", "Money left"]);
  });

  it("puts each task in its column for every grouping", () => {
    const task = makeRow({ status: "in_progress", priority: "high", project_id: "p2", created_by_bot: "b1", category: "Home", due_bucket: "tomorrow" });
    expect(columnOf(task, "status")).toBe("in_progress");
    expect(columnOf(makeRow({ status: "done" }), "status")).toBe("done");
    expect(columnOf(makeRow({ status: "todo" }), "status")).toBe("todo");
    expect(columnOf(task, "priority")).toBe("high");
    expect(columnOf(task, "project")).toBe("p2");
    expect(columnOf(makeRow({ project_id: null }), "project")).toBe("none");
    expect(columnOf(task, "bot")).toBe("b1");
    expect(columnOf(makeRow({ created_by_bot: null }), "bot")).toBe("you");
    expect(columnOf(task, "list")).toBe("Home");
    expect(columnOf(makeRow({ category: null }), "list")).toBe("none");
    expect(columnOf(task, "due")).toBe("tomorrow");
  });

  it("lists the columns in order", () => {
    expect(keys("status")).toEqual(["todo", "in_progress", "done"]);
    expect(columnsFor("status", CTX).map((c) => c.label)).toEqual(["To do", "On it", "Done"]);
    expect(keys("due")).toEqual(["overdue", "today", "tomorrow", "week", "later", "none"]);
    expect(columnsFor("due", CTX).map((c) => c.label)).toEqual(["Overdue", "Today", "Tomorrow", "This week", "Later", "No date"]);
    expect(keys("priority")).toEqual(["urgent", "high", "medium", "low"]);
  });

  it("lists projects with tasks, then No project; bots that made a task after You; lists A-Z then No list", () => {
    const tasks = [makeRow({ project_id: "p2", created_by_bot: "b2", category: "zeta" }), makeRow({ id: "t2", category: "Alpha" })];
    expect(keys("project", { ...CTX, tasks })).toEqual(["p2", "none"]);
    expect(keys("project", { ...CTX, tasks: [] })).toEqual(["none"]);
    expect(keys("bot", { ...CTX, tasks })).toEqual(["you", "b2"]);
    expect(keys("list", { ...CTX, tasks })).toEqual(["Alpha", "zeta", "none"]);
    expect(columnsFor("list", { ...CTX, tasks }).at(-1)?.label).toBe("No list");
    expect(columnsFor("project", { ...CTX, tasks })[0]).toMatchObject({ label: "Lisbon", color: "#3b82f6" });
  });

  it("a move sets the grouped field: status, due, project, priority, list", () => {
    expect(moveFor("status", "todo")).toEqual({ kind: "patch", patch: { status: "todo" } });
    expect(moveFor("status", "in_progress")).toEqual({ kind: "patch", patch: { status: "in_progress" } });
    expect(moveFor("status", "done")).toEqual({ kind: "complete" });
    const done = makeRow({ status: "done" });
    expect(moveFor("status", "todo", done)).toEqual({ kind: "reopen" });
    expect(moveFor("status", "in_progress", done)).toEqual({ kind: "reopen", then: { status: "in_progress" } });
    expect(moveFor("due", "today", undefined, TODAY)).toEqual({ kind: "day", day: "2026-10-20" });
    expect(moveFor("due", "tomorrow", undefined, TODAY)).toEqual({ kind: "day", day: "2026-10-21" });
    expect(moveFor("due", "none", undefined, TODAY)).toEqual({ kind: "day", day: null });
    expect(moveFor("project", "p1")).toEqual({ kind: "patch", patch: { project_id: "p1" } });
    expect(moveFor("project", "none")).toEqual({ kind: "patch", patch: { project_id: null } });
    expect(moveFor("priority", "urgent")).toEqual({ kind: "patch", patch: { priority: "urgent" } });
    expect(moveFor("list", "Home")).toEqual({ kind: "patch", patch: { category: "Home" } });
    expect(moveFor("list", "none")).toEqual({ kind: "patch", patch: { category: null } });
  });

  it("Overdue and Bot columns are not drop targets", () => {
    expect(columnsFor("due", CTX).find((c) => c.key === "overdue")?.dropTarget).toBe(false);
    expect(columnsFor("due", CTX).find((c) => c.key === "today")?.dropTarget).toBe(true);
    expect(columnsFor("bot", { ...CTX, tasks: [makeRow()] }).every((c) => !c.dropTarget)).toBe(true);
    expect(moveFor("due", "overdue", undefined, TODAY)).toEqual({ kind: "none" });
    expect(moveFor("bot", "b1")).toEqual({ kind: "none" });
  });

  it("This week and Later ask for a day", () => {
    expect(moveFor("due", "week", undefined, TODAY)).toEqual({ kind: "pick-day" });
    expect(moveFor("due", "later", undefined, TODAY)).toEqual({ kind: "pick-day" });
  });

  it("Done has no + , and neither does Overdue", () => {
    expect(columnsFor("status", CTX).map((c) => c.canAdd)).toEqual([true, true, false]);
    expect(columnsFor("due", CTX).map((c) => c.canAdd)).toEqual([false, true, true, true, true, true]);
  });

  it("hides finished tasks from the past when grouped by Due date", () => {
    const old = makeRow({ id: "a", status: "done", due_bucket: "overdue" });
    const fresh = makeRow({ id: "b", status: "done", due_bucket: "today" });
    const open = makeRow({ id: "c", due_bucket: "overdue" });
    expect(visibleTasks([old, fresh, open], "due").map((t) => t.id)).toEqual(["b", "c"]);
    expect(visibleTasks([old, fresh, open], "status")).toHaveLength(3);
  });
});
