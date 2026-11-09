import { describe, expect, it } from "vitest";
import { buildDayMarks, cellWords, dayPlan, dotTone, reminderFires } from "../src/components/board/calendar/dayMarks";
import { placeTasks } from "../src/components/board/calendar/taskPlacement";
import { monthDays } from "../src/components/board/calendar/monthCells";
import type { RoutineDays } from "../src/lib/routineDays";
import { makeRow as task } from "./taskFixtures";

const TODAY = "2026-10-20";
const DAYS = monthDays("2026-10");
const plain = { reminder_at: null, pre_reminders: [] };

describe("reminderFires", () => {
  it("turns the reminder and each advance one into Madrid days and times, once each", () => {
    const one = task({ reminder_at: "2026-10-23T22:30:00+00:00", pre_reminders: ["2026-10-22T21:00:00+00:00", "-1h", "-1d", "nonsense", "-1h"] });
    expect(reminderFires(one)).toEqual([
      { day: "2026-10-22", time: "23:00" },
      { day: "2026-10-23", time: "00:30" }, // -1d
      { day: "2026-10-23", time: "23:30" }, // -1h
      { day: "2026-10-24", time: "00:30" },
    ]);
  });

  it("has none for a closed task or one with no readable reminder", () => {
    expect(reminderFires(task({ status: "done", reminder_at: "2026-10-23T08:00:00Z" }))).toEqual([]);
    expect(reminderFires(task(plain))).toEqual([]);
    expect(reminderFires(task({ reminder_at: "soon", pre_reminders: [] }))).toEqual([]);
  });

  it("reads days and hours together in an offset", () => {
    expect(reminderFires(task({ reminder_at: "2026-10-23T10:00:00Z", pre_reminders: ["-1d2h"] }))).toEqual([
      { day: "2026-10-22", time: "10:00" },
      { day: "2026-10-23", time: "12:00" },
    ]);
  });
});

describe("buildDayMarks", () => {
  const routines: RoutineDays = new Map([["2026-10-22", [{ routineId: "r1", routineName: "News", botId: "b2", botName: "Scout", times: ["09:00"] }]]]);
  const rows = [
    task({ id: "a", due_date: "2026-10-22", created_by_bot: "b1", ...plain }),
    task({ id: "b", due_date: "2026-10-22T09:30:00+02:00", reminder_at: "2026-10-22T07:00:00Z", pre_reminders: ["-30m"] }),
    task({ id: "c", due_date: "2026-10-22", created_by_bot: "b3", ...plain }),
    task({ id: "late", due_date: "2026-10-10", ...plain }),
  ];

  it("counts tasks, reminders (per task), routines and at most two bots per day; a late one sits on today", () => {
    const marks = buildDayMarks({ placed: placeTasks(rows, TODAY, DAYS), tasks: rows, routines });
    const thu = marks.get("2026-10-22");
    expect(thu?.tasks.map((t) => t.id)).toEqual(["b", "a", "c"]);
    expect(thu?.reminders).toBe(1);
    expect(thu?.routines).toBe(1);
    expect(thu?.botIds).toEqual(["b1", "b3"]);
    expect(marks.get(TODAY)?.tasks.map((t) => t.id)).toEqual(["late"]);
    expect(marks.get("2026-10-10")).toBeUndefined();
    expect(cellWords("2026-10-22", thu)).toBe("Thu 22 Oct: 3 tasks, 1 reminder, 1 routine");
    expect(cellWords("2026-10-25", undefined)).toBe("Sun 25 Oct");
  });

  it("puts a reminder on its own day even when the task is due another day", () => {
    const later = task({ id: "x", due_date: "2026-11-30", reminder_at: "2026-10-25T08:00:00Z", pre_reminders: [] });
    const marks = buildDayMarks({ placed: placeTasks([later], TODAY, DAYS), tasks: [later], routines: new Map() });
    expect(marks.get("2026-10-25")).toMatchObject({ tasks: [], reminders: 1, routines: 0, botIds: [] });
  });
});

describe("dotTone", () => {
  const project = { name: "Casa", color: "#22c55e" };
  it("late beats priority beats project; done is a ring", () => {
    expect(dotTone(task({ due_date: "2026-10-10", priority: "urgent" }), TODAY, project)).toEqual({ kind: "late" });
    expect(dotTone(task({ due_date: "2026-10-22", priority: "urgent" }), TODAY, project)).toEqual({ kind: "urgent" });
    expect(dotTone(task({ due_date: "2026-10-22", priority: "high" }), TODAY, undefined)).toEqual({ kind: "high" });
    expect(dotTone(task({ due_date: "2026-10-22" }), TODAY, project)).toEqual({ kind: "project", color: "#22c55e" });
    expect(dotTone(task({ due_date: "2026-10-22" }), TODAY, undefined)).toEqual({ kind: "plain" });
    expect(dotTone(task({ due_date: "2026-10-22", status: "done" }), TODAY, project)).toEqual({ kind: "done" });
  });
});

describe("dayPlan", () => {
  it("lists the day's tasks by time (All day last, Late on today), its reminders and its routines", () => {
    const rows = [
      task({ id: "all", title: "Laundry", due_date: "2026-10-20", ...plain }),
      task({ id: "lunch", title: "Lunch", due_date: "2026-10-20T13:30:00+02:00", reminder_at: "2026-10-20T11:30:00Z", pre_reminders: ["-30m"] }),
      task({ id: "late", title: "Deposit", due_date: "2026-10-16", ...plain }),
    ];
    const plan = dayPlan(TODAY, { placed: placeTasks(rows, TODAY, DAYS), tasks: rows, routines: new Map(), today: TODAY });
    expect(plan.tasks.map((r) => `${r.time} ${r.task.id}`)).toEqual(["Late late", "13:30 lunch", "All day all"]);
    expect(plan.reminders.map((r) => `${r.time} ${r.more} ${r.task.id}`)).toEqual(["13:00 1 lunch"]);
    expect(plan.routines).toEqual([]);
  });
});
