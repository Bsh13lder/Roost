import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QuickAdd } from "../src/components/tasks/QuickAdd";
import { makeRichLine } from "./quickRichFixtures";
import { makeTask } from "./taskFixtures";

const parseQuickLineMock = vi.fn();
vi.mock("../src/api/projects", () => ({
  listProjects: () => Promise.resolve([
    { id: "p1", name: "Renovation", status: "active" }, { id: "p2", name: "Trip", status: "active" },
  ]),
}));
vi.mock("../src/api/dates", () => ({ parseDate: () => Promise.resolve({ ok: true, day: "2026-10-30", time: "09:00" }) }));
vi.mock("../src/hooks/useLiveStore", () => ({ useLiveState: () => ({ bots: {}, boardVersion: { money: 0, tasks: 0 } }) }));
vi.mock("../src/api/tasks", () => ({
  parseQuickLine: (...a: unknown[]) => parseQuickLineMock(...a),
  createTask: vi.fn(),
  listTasks: () => Promise.resolve([makeTask({ tags: ["shopping", "home"] })]),
}));

beforeEach(() => parseQuickLineMock.mockReset().mockResolvedValue(makeRichLine({ title: "Call Ana", ready: true })));
afterEach(() => cleanup());

async function typed(text: string) {
  const user = userEvent.setup();
  render(<QuickAdd onAdded={vi.fn()} />);
  const box = screen.getByLabelText("New task");
  await user.type(box, text);
  return { user, box };
}

describe("the quick add's manual pickers", () => {
  it("has a button for each of date, project, priority, tag and repeat", () => {
    render(<QuickAdd onAdded={vi.fn()} />);
    const group = screen.getByRole("group", { name: "Add details" });
    for (const name of ["Date", "Project", "Priority", "Tag", "Repeat"]) {
      expect(within(group).getByRole("button", { name })).toBeInTheDocument();
    }
  });

  it("Priority writes the same words as typing !high", async () => {
    const { user, box } = await typed("Call Ana");
    await user.click(screen.getByRole("button", { name: "Priority" }));
    await user.click(await screen.findByRole("menuitem", { name: "High" }));
    expect(box).toHaveValue("Call Ana !high");
  });

  it("Repeat writes repeat words", async () => {
    const { user, box } = await typed("Water plants");
    await user.click(screen.getByRole("button", { name: "Repeat" }));
    await user.click(await screen.findByRole("menuitem", { name: "Every other week" }));
    expect(box).toHaveValue("Water plants every other week");
  });

  it("Project searches the list and writes /Name, replacing an earlier project's words", async () => {
    parseQuickLineMock.mockResolvedValue(makeRichLine({ title: "Call Ana", ready: true, matches: { project: ["/Trip"] } }));
    const { user, box } = await typed("Call Ana /Trip");
    await waitFor(() => expect(parseQuickLineMock).toHaveBeenCalled());
    await new Promise((resolve) => setTimeout(resolve, 20)); // the reading lands in state
    await user.click(screen.getByRole("button", { name: "Project" }));
    const list = await screen.findByRole("dialog", { name: "Pick a project" });
    expect(await within(list).findByRole("button", { name: "Renovation" })).toBeInTheDocument();
    await user.type(within(list).getByLabelText("Search projects"), "ren");
    expect(within(list).queryByRole("button", { name: "Trip" })).not.toBeInTheDocument();
    await user.click(within(list).getByRole("button", { name: "Renovation" }));
    expect(box).toHaveValue("Call Ana /Renovation");
  });

  it("Tag offers existing tags and makes new ones", async () => {
    const { user, box } = await typed("Milk");
    await user.click(screen.getByRole("button", { name: "Tag" }));
    const panel = await screen.findByRole("dialog", { name: "Pick a tag" });
    await user.click(await within(panel).findByRole("button", { name: "#shopping" }));
    expect(box).toHaveValue("Milk #shopping");
    await user.click(screen.getByRole("button", { name: "Tag" }));
    const again = await screen.findByRole("dialog", { name: "Pick a tag" });
    await user.type(within(again).getByLabelText("Tag"), "garden{Enter}");
    expect(box).toHaveValue("Milk #shopping #garden");
  });

  it("Date writes the picked day and time", async () => {
    const { user, box } = await typed("Call Ana");
    await user.click(screen.getByRole("button", { name: "Date" }));
    const panel = await screen.findByRole("dialog", { name: "Pick a date" });
    await user.type(within(panel).getByLabelText("Due date"), "2026-10-30 09:00");
    await user.click(within(panel).getByRole("button", { name: "Use this date" }));
    expect(box).toHaveValue("Call Ana 2026-10-30 at 09:00");
  });
});
