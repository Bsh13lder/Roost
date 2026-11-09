import { describe, expect, it } from "vitest";
import { groupsFor, projectGroups } from "../src/components/board/groupTasks";
import { makeRow } from "./taskFixtures";

const TODAY = "2026-10-20";
const row = (id: string, due: string | null, extra = {}) => makeRow({ id, title: id, due_date: due, ...extra });
const ids = (rows: readonly { id: string }[]) => rows.map((r) => r.id);

describe("groupsFor", () => {
  it("groups each view as the mockup does", () => {
    const late = row("late", "2026-10-18");
    const now = row("now", "2026-10-20T09:00:00+02:00");
    const tomorrow = row("tom", "2026-10-21");
    const later = row("later", "2026-10-22");
    const also = row("also", "2026-10-22");
    const undated = row("undated", null);
    const done = row("done", "2026-10-19", { status: "done" });

    const today = groupsFor("today", [late, now], TODAY);
    expect(today.map((g) => [g.title, g.tone, g.action, ids(g.rows)])).toEqual([
      ["Overdue", "danger", "reschedule-all", ["late"]],
      ["Due today · Tue 20 Oct", undefined, undefined, ["now"]],
    ]);

    const upcoming = groupsFor("upcoming", [tomorrow, later, also], TODAY);
    expect(upcoming.map((g) => [g.title, ids(g.rows)])).toEqual([
      ["Tomorrow · Wed 21 Oct", ["tom"]], ["Thu 22 Oct", ["later", "also"]],
    ]);

    expect(groupsFor("overdue", [late], TODAY).map((g) => [g.title, g.tone, g.action])).toEqual([["Overdue", "danger", "reschedule-all"]]);
    expect(groupsFor("someday", [undated], TODAY).map((g) => g.title)).toEqual(["No date"]);
    expect(groupsFor("done", [done], TODAY).map((g) => g.title)).toEqual(["Done"]);
  });

  it("leaves out an empty group and keeps the server's order inside a day", () => {
    const groups = groupsFor("today", [row("now", "2026-10-20")], TODAY);
    expect(groups.map((g) => g.title)).toEqual(["Due today · Tue 20 Oct"]);
    expect(groupsFor("upcoming", [], TODAY)).toEqual([]);
  });
});

describe("projectGroups", () => {
  it("project groups use seven days for Next up", () => {
    const rows = [
      row("late", "2026-10-19"), row("today", "2026-10-20"), row("six", "2026-10-26"), row("seven", "2026-10-27"),
      row("none", null), row("fin", "2026-10-01", { status: "done" }), row("bad", null, { status: "failed" }),
    ];
    const groups = projectGroups(rows, TODAY);
    expect(groups.map((g) => [g.title, g.tone, ids(g.rows)])).toEqual([
      ["Overdue", "danger", ["late"]],
      ["Next up", undefined, ["today", "six"]],
      ["Later", undefined, ["seven", "none"]],
      ["Done", undefined, ["fin", "bad"]],
    ]);
  });
});
