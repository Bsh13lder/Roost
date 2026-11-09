import { describe, expect, it } from "vitest";
import { blockerOf, chipsOf, taskInputOf } from "../src/components/tasks/quickChips";
import { makeQuickLine } from "./taskFixtures";
import { makeRichLine } from "./quickRichFixtures";

const RENOVATION = { id: "p1", name: "Renovation", currency: "EUR", color: "#3b82f6" };

describe("the quick add's chips (redesign P3)", () => {
  it("draws the date, project, budget and priority the server read", () => {
    const line = makeQuickLine({
      title: "Call plumber", due_date: "2026-10-21T09:00:00+02:00", priority: "high", project: RENOVATION,
      project_words: "/Renovation", budget: "200.00", budget_words: "€200", ready: true,
    });
    expect(chipsOf(line)).toEqual([
      { kind: "date", label: "Wed 21 Oct 2026, 09:00", tone: "read" },
      { kind: "project", label: "/Renovation", tone: "read" },
      { kind: "budget", label: "€200.00", tone: "read" },
      { kind: "priority", label: "!high", tone: "read" },
    ]);
    expect(taskInputOf(line)).toEqual({
      title: "Call plumber", due_date: "2026-10-21T09:00:00+02:00", priority: "high", project_id: "p1",
      allocated_budget: "200.00",
    });
    expect(blockerOf(line)).toBeNull();
  });

  it("shows words it could not use as typed, to fix, with the server's reason", () => {
    const line = makeQuickLine({
      title: "Paint", project_words: "/Renovaton", budget_words: "€20",
      project_question: "No project is called “Renovaton”. Did you mean “Renovation”? Say it exactly.",
    });
    expect(chipsOf(line)).toEqual([
      { kind: "project", label: "/Renovaton", tone: "ask" }, { kind: "budget", label: "€20", tone: "ask" },
    ]);
    expect(blockerOf(line)).toContain("Did you mean “Renovation”?");
    expect(blockerOf(makeQuickLine({ title: "", ready: false }))).toBe("Give the task a title.");
    expect(taskInputOf(makeQuickLine({ title: "Buy milk", ready: true }))).toEqual({ title: "Buy milk" });
  });

  it("draws the star, estimate, reminder, repeat and warnings, and adds exactly them", () => {
    const line = makeRichLine({
      title: "Call plumber", due_date: "2026-10-21T09:00:00+02:00", starred: true, estimate_minutes: 90,
      reminder_at: "2026-10-21T06:30:00+00:00", reminder_words: "^30m before", recurring: "0 9 * * 1",
      repeat_text: "every Monday 09:00", repeat_words: "every Monday", warnings: ["Two priorities: kept !low."],
      priority: "low", ready: true,
    });
    expect(chipsOf(line).map((chip) => [chip.kind, chip.label, chip.tone])).toEqual([
      ["date", "Wed 21 Oct 2026, 09:00", "read"], ["reminder", "Remind Wed 21 Oct 2026, 08:30", "read"],
      ["repeat", "every Monday 09:00", "read"], ["priority", "!low", "read"], ["star", "Starred", "read"],
      ["estimate", "~1h 30m", "read"], ["warning", "Two priorities: kept !low.", "warn"],
    ]);
    expect(taskInputOf(line)).toEqual({
      title: "Call plumber", due_date: "2026-10-21T09:00:00+02:00", priority: "low", starred: true,
      estimate_minutes: 90, reminder_at: "2026-10-21T06:30:00+00:00", recurring: "0 9 * * 1",
    });
    expect(blockerOf(line)).toBeNull();
  });

  it("asks about a repeat it cannot say and a bot it cannot find, and a reminder that failed only warns", () => {
    const repeat = makeRichLine({
      title: "Clean", repeat_words: "every 2 weeks", repeat_problem: "Repeats can be daily, weekdays, weekly, monthly or yearly.",
    });
    expect(chipsOf(repeat)).toEqual([{ kind: "repeat", label: "every 2 weeks", tone: "ask" }]);
    expect(blockerOf(repeat)).toBe("Repeats can be daily, weekdays, weekly, monthly or yearly.");
    const bot = makeRichLine({ title: "Pay", assignee_words: "@Nobody", assignee_question: "No bot is called “Nobody”." });
    expect(chipsOf(bot)).toEqual([{ kind: "assignee", label: "@Nobody", tone: "ask" }]);
    expect(blockerOf(bot)).toBe("No bot is called “Nobody”.");
    const reminder = makeRichLine({ title: "Pay", reminder_words: "^1h before", ready: true, warnings: ["“^1h before” needs a due date."] });
    expect(chipsOf(reminder).map((chip) => chip.tone)).toEqual(["warn", "warn"]);
    expect(blockerOf(reminder)).toBeNull();
  });

  it("hands a task to a bot only once that bot is confirmed", () => {
    const line = makeRichLine({ title: "Call", ready: true, assignee: { id: "b1", name: "Scout" }, assignee_words: "@Scout" });
    expect(chipsOf(line)).toEqual([{ kind: "assignee", label: "Assign to Scout", tone: "read", confirm: { id: "b1", name: "Scout" } }]);
    expect(blockerOf(line)).toBe("Confirm handing this to Scout first.");
    expect(taskInputOf(line)).toEqual({ title: "Call" });
    expect(chipsOf(line, "b1")).toEqual([{ kind: "assignee", label: "Handing to Scout", tone: "read" }]);
    expect(blockerOf(line, "b1")).toBeNull();
    expect(taskInputOf(line, "b1")).toEqual({ title: "Call", assign_bot_id: "b1", assign_confirmed: true });
    expect(blockerOf(line, "other")).toBe("Confirm handing this to Scout first.");
  });

  it("draws a rule's words and sends its rule and end", () => {
    const rule = '{"v":1,"every":2,"unit":"week","weekday":0,"from_completion":false}';
    const line = makeRichLine({
      title: "Gym", due_date: "2026-10-26T09:00:00+01:00", recurring: rule, recur_until: "2027-01-31",
      repeat_text: "every other Monday, until Sun 31 Jan 2027", repeat_words: "every other Monday", ready: true,
    });
    expect(chipsOf(line).find((chip) => chip.kind === "repeat")?.label).toBe("every other Monday, until Sun 31 Jan 2027");
    expect(taskInputOf(line)).toMatchObject({ recurring: rule, recur_until: "2027-01-31" });
  });

  it("reads a budget in no project in General's currency and adds it (owner, 2026-10-26)", () => {
    const line = makeRichLine({ title: "Buy shoes", budget: "30.00", budget_words: "€30", budget_currency: "EUR", ready: true });
    expect(chipsOf(line)).toEqual([{ kind: "budget", label: "€30.00", tone: "read" }]);
    expect(taskInputOf(line)).toEqual({ title: "Buy shoes", allocated_budget: "30.00" });
    expect(blockerOf(line)).toBeNull();
    const foreign = makeRichLine({
      title: "Buy shoes", budget_words: "$30", ready: false,
      budget_problem: "“General” keeps its money in EUR: write the budget in EUR.",
    });
    expect(chipsOf(foreign)).toEqual([{ kind: "budget", label: "$30", tone: "ask" }]);
    expect(blockerOf(foreign)).toBe("“General” keeps its money in EUR: write the budget in EUR.");
  });

  it("shows the sum a budget was worked out from", () => {
    const line = makeRichLine({ title: "Paint walls", project: RENOVATION, budget: "135.00", budget_words: "€3x45", budget_math: "3×45", ready: true });
    expect(chipsOf(line).find((chip) => chip.kind === "budget")?.label).toBe("€135.00 = 3×45");
    expect(taskInputOf(line)).toMatchObject({ allocated_budget: "135.00" });
  });

  it("shows the server's resolved dates in Madrid words", () => {
    const line = makeRichLine({
      title: "Call", due_date: "2026-10-21T09:00:00+02:00", due_text: "Wed 21 Oct 09:00",
      reminder_at: "2026-10-21T06:30:00+00:00", reminder_text: "Wed 21 Oct 08:30", ready: true,
    });
    expect(chipsOf(line).map((chip) => chip.label)).toEqual(["Wed 21 Oct 09:00", "Remind Wed 21 Oct 08:30"]);
  });
});
