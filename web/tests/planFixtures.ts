import type { PlanItemOut, PlanOut } from "../src/api/plan";

export const item = (over: Partial<PlanItemOut> = {}): PlanItemOut => ({
  id: "i-1", status: "planned", text: "Call the plumber", tags: [], date: null, time: null, done_on: null, dropped_on: null,
  scheduled: null, indent: 0, line_no: 1, tainted: false, ...over,
});

export const plan = (over: Partial<PlanOut> = {}): PlanOut => ({
  content: "- [ ] Call the plumber ^i-1\n", revision: 3, unreadable: 0,
  items: [
    item(),
    item({ id: "i-2", status: "on_it", text: "Write the report", date: "2026-10-21", time: "15:00" }),
    item({ id: "i-3", status: "done", text: "Pay rent", date: "2026-10-21", time: "09:30", done_on: "2026-10-21" }),
    item({ id: "i-4", status: "dropped", text: "Old idea" }),
  ],
  ...over,
});
