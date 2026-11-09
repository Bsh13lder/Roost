import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QuickAdd } from "../src/components/tasks/QuickAdd";
import type { QuickLineOut } from "../src/api/types";
import { makeQuickLine, makeTask } from "./taskFixtures";
import { makeRichLine } from "./quickRichFixtures";

const parseQuickLineMock = vi.fn();
const createTaskMock = vi.fn();
const listProjectsMock = vi.fn();
const listTasksMock = vi.fn();
vi.mock("../src/api/projects", () => ({ listProjects: (...a: unknown[]) => listProjectsMock(...a) }));
vi.mock("../src/hooks/useLiveStore", () => ({
  useLiveState: () => ({
    boardVersion: { money: 0, tasks: 0 },
    bots: { b1: { id: "b1", name: "Scout" }, b2: { id: "b2", name: "Money Bot" } },
  }),
}));
vi.mock("../src/api/tasks", () => ({
  parseQuickLine: (...a: unknown[]) => parseQuickLineMock(...a),
  createTask: (...a: unknown[]) => createTaskMock(...a),
  listTasks: (...a: unknown[]) => listTasksMock(...a),
}));

const RENOVATION = { id: "p1", name: "Renovation", currency: "EUR", color: "#3b82f6" };
const LINE = "Call plumber tomorrow 9am /Renovation €200 !high";
const READ: QuickLineOut = makeRichLine({
  title: "Call plumber", due_date: "2026-10-21T09:00:00+02:00", priority: "high", project: RENOVATION,
  project_words: "/Renovation", budget: "200.00", budget_words: "€200", ready: true,
});
const onAdded = vi.fn();

// The server, as far as these tests need it: the full line reads as READ; "Book 2 tickets" reads the 2 as a
// date unless the date is skipped.
function server({ text, skip = [] }: { text: string; skip?: string[] }): Promise<QuickLineOut> {
  if (text === LINE) return Promise.resolve(READ);
  if (text === "Book 2 tickets") {
    return Promise.resolve(skip.includes("date")
      ? makeQuickLine({ title: "Book 2 tickets", ready: true })
      : makeQuickLine({ title: "Book tickets", due_date: "2026-11-02", ready: true }));
  }
  return Promise.resolve(makeQuickLine({ title: text.trim(), ready: Boolean(text.trim()) }));
}

beforeEach(() => {
  listProjectsMock.mockReset().mockResolvedValue([
    { id: "p1", name: "Renovation", status: "active" }, { id: "p2", name: "Trip", status: "active" },
  ]);
  parseQuickLineMock.mockReset().mockImplementation(server);
  createTaskMock.mockReset().mockResolvedValue(makeTask());
  onAdded.mockReset();
  listTasksMock.mockReset().mockResolvedValue([
    makeTask({ tags: ["shopping", "home"] }), makeTask({ tags: ["Shopping"] }),
  ]);
});
afterEach(() => cleanup());

describe("the quick add (redesign P3)", () => {
  it("sits in the quick box with the + glyph and the ? help", () => {
    render(<QuickAdd onAdded={onAdded} />);
    const box = screen.getByRole("group", { name: "Add a task" });
    expect(box).toHaveClass("quick-box");
    expect(box.querySelector(".quick-box__glyph")).toHaveTextContent("+");
    expect(within(box).getByRole("button", { name: "Quick line help" })).toBeInTheDocument();
    expect(within(box).getByLabelText("New task")).toHaveAttribute(
      "placeholder", "Add a task… try “Call plumber friday 9am /Casa Nueva €200 !!”");
  });

  it("turns the line into chips as you type, then adds exactly what the server read", async () => {
    const user = userEvent.setup();
    render(<QuickAdd onAdded={onAdded} />);
    await user.type(screen.getByLabelText("New task"), LINE);
    expect(await screen.findByText("Wed 21 Oct 2026, 09:00")).toHaveClass("quick-chip--read");
    for (const chip of ["/Renovation", "€200.00", "!high"]) expect(screen.getByText(chip)).toBeInTheDocument();
    expect(screen.getByText("Call plumber")).toHaveClass("quick-add__title");
    await user.keyboard("{Enter}");
    expect(createTaskMock).toHaveBeenCalledWith({
      title: "Call plumber", due_date: "2026-10-21T09:00:00+02:00", priority: "high", project_id: "p1",
      allocated_budget: "200.00",
    });
    await waitFor(() => expect(onAdded).toHaveBeenCalled());
    expect(screen.getByLabelText("New task")).toHaveValue("");
    expect(parseQuickLineMock).toHaveBeenLastCalledWith({ text: LINE });
  });

  it("draws only the newest reading, even when an older answer arrives last", async () => {
    let releaseOld: (line: QuickLineOut) => void = () => undefined;
    parseQuickLineMock.mockImplementation((input: { text: string }) => (input.text === "Book 2"
      ? new Promise<QuickLineOut>((resolve) => { releaseOld = resolve; })
      : server(input)));
    const user = userEvent.setup();
    render(<QuickAdd onAdded={onAdded} />);
    const box = screen.getByLabelText("New task");
    await user.type(box, "Book 2");
    await waitFor(() => expect(parseQuickLineMock).toHaveBeenCalledWith({ text: "Book 2" }));
    await user.type(box, " tickets");
    expect(await screen.findByText("Book tickets")).toBeInTheDocument();
    await act(async () => releaseOld(makeQuickLine({ title: "Stale", ready: true })));
    expect(screen.queryByText("Stale")).not.toBeInTheDocument();
    expect(screen.getByText("Book tickets")).toBeInTheDocument();
  });

  it("a removed chip's words go back into the title, and the line is read again without it", async () => {
    const user = userEvent.setup();
    render(<QuickAdd onAdded={onAdded} />);
    await user.type(screen.getByLabelText("New task"), "Book 2 tickets");
    expect(await screen.findByText("Book tickets")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Remove Mon 2 Nov 2026" }));
    await waitFor(() => expect(parseQuickLineMock).toHaveBeenLastCalledWith({ text: "Book 2 tickets", skip: ["date"] }));
    await waitFor(() => expect(screen.queryByText("Mon 2 Nov 2026")).not.toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "Add" }));
    expect(createTaskMock).toHaveBeenCalledWith({ title: "Book 2 tickets" });
  });

  it("adds nothing while the server has a question, and says it", async () => {
    parseQuickLineMock.mockResolvedValue(makeQuickLine({
      title: "Paint", project_words: "/Renovaton",
      project_question: "No project is called “Renovaton”. Did you mean “Renovation”? Say it exactly.",
    }));
    const user = userEvent.setup();
    render(<QuickAdd onAdded={onAdded} />);
    await user.type(screen.getByLabelText("New task"), "Paint /Renovaton{Enter}");
    expect(await screen.findByText(/Did you mean “Renovation”\?/)).toBeInTheDocument();
    expect(await screen.findByText("/Renovaton")).toHaveClass("quick-chip--ask");
    expect(createTaskMock).not.toHaveBeenCalled();
  });

  it("on a project's page, reads the line with the page's project", async () => {
    const user = userEvent.setup();
    render(<QuickAdd projectId="p1" onAdded={onAdded} />);
    await user.type(screen.getByLabelText("New task"), "Buy seeds{Enter}");
    await waitFor(() => expect(createTaskMock).toHaveBeenCalled());
    expect(parseQuickLineMock).toHaveBeenLastCalledWith({ text: "Buy seeds", project_id: "p1" });
  });

  it("Tab and Enter accept a suggestion, Esc closes it", async () => {
    const user = userEvent.setup();
    render(<QuickAdd onAdded={onAdded} />);
    const box = screen.getByLabelText("New task");
    await user.type(box, "Paint /re");
    expect(await screen.findByRole("option", { name: "Renovation" })).toBeInTheDocument();
    expect(box).toHaveAttribute("aria-expanded", "true");
    await user.keyboard("{Tab}");
    expect(box).toHaveValue("Paint /Renovation ");
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
    await user.type(box, "@s");
    expect(await screen.findByRole("option", { name: "Scout" })).toBeInTheDocument();
    await user.keyboard("{Enter}");
    expect(box).toHaveValue("Paint /Renovation @Scout ");
    expect(createTaskMock).not.toHaveBeenCalled();
    await user.type(box, "!");
    expect(await screen.findByRole("listbox")).toBeInTheDocument();
    await user.keyboard("{ArrowDown}");
    expect(box.getAttribute("aria-activedescendant")).toMatch(/option-1$/);
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
    expect(box).toHaveValue("Paint /Renovation @Scout !");
  });

  it("Enter is blocked until the bot chip is confirmed", async () => {
    parseQuickLineMock.mockImplementation(() => Promise.resolve(makeRichLine({
      title: "Call plumber", ready: true, assignee: { id: "b1", name: "Scout" }, assignee_words: "@Scout",
    })));
    const user = userEvent.setup();
    render(<QuickAdd onAdded={onAdded} />);
    const box = screen.getByLabelText("New task");
    await user.type(box, "Call plumber @Scout ");
    expect(await screen.findByRole("button", { name: "Assign to Scout" })).toBeInTheDocument();
    await user.keyboard("{Enter}");
    expect((await screen.findAllByText("Confirm handing this to Scout first.")).length).toBeGreaterThan(0);
    expect(createTaskMock).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Assign to Scout" }));
    expect(screen.getByText("Handing to Scout")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Add" }));
    await waitFor(() => expect(createTaskMock).toHaveBeenCalledWith({
      title: "Call plumber", assign_bot_id: "b1", assign_confirmed: true,
    }));
  });

  it("shows a warning chip and never blocks on it", async () => {
    parseQuickLineMock.mockResolvedValue(makeRichLine({ title: "Dinner", priority: "low", ready: true, warnings: ["Two priorities: kept !low."] }));
    const user = userEvent.setup();
    render(<QuickAdd onAdded={onAdded} />);
    await user.type(screen.getByLabelText("New task"), "Dinner !high !low");
    const warning = await screen.findByText("Two priorities: kept !low.");
    expect(warning.closest(".quick-chip")).toHaveClass("quick-chip--warn");
    expect(screen.queryByRole("button", { name: "Remove Two priorities: kept !low." })).not.toBeInTheDocument();
    await user.keyboard("{Enter}");
    await waitFor(() => expect(createTaskMock).toHaveBeenCalled());
  });

  it("× on a chip sends that kind in skip", async () => {
    parseQuickLineMock.mockImplementation(({ skip = [] }: { skip?: string[] }) => Promise.resolve(skip.includes("star")
      ? makeRichLine({ title: "Call Ana *", ready: true })
      : makeRichLine({ title: "Call Ana", ready: true, starred: true, estimate_minutes: 60 })));
    const user = userEvent.setup();
    render(<QuickAdd onAdded={onAdded} />);
    await user.type(screen.getByLabelText("New task"), "Call Ana * ~1h");
    expect(await screen.findByText("Starred")).toBeInTheDocument();
    expect(screen.getByText("~1h")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Remove Starred" }));
    await waitFor(() => expect(parseQuickLineMock).toHaveBeenLastCalledWith({ text: "Call Ana * ~1h", skip: ["star"] }));
    await waitFor(() => expect(screen.queryByText("Starred")).not.toBeInTheDocument());
  });

  it("removing the p1 chip puts its words back in the title that is added", async () => {
    parseQuickLineMock.mockImplementation(({ skip = [] }: { skip?: string[] }) => Promise.resolve(skip.includes("priority")
      ? makeRichLine({ title: "Pay rent p1", ready: true })
      : makeRichLine({ title: "Pay rent", ready: true, priority: "urgent" })));
    const user = userEvent.setup();
    render(<QuickAdd onAdded={onAdded} />);
    await user.type(screen.getByLabelText("New task"), "Pay rent p1");
    await user.click(await screen.findByRole("button", { name: "Remove !urgent" }));
    await waitFor(() => expect(screen.queryByText("!urgent")).not.toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "Add" }));
    await waitFor(() => expect(createTaskMock).toHaveBeenCalledWith({ title: "Pay rent p1" }));
  });

  it("# suggests the tags tasks already carry, most used first, and / suggests projects", async () => {
    const user = userEvent.setup();
    render(<QuickAdd onAdded={onAdded} />);
    const box = screen.getByLabelText("New task");
    await user.type(box, "Milk #");
    const options = await screen.findAllByRole("option");
    expect(options.map((option) => option.textContent)).toEqual(["shopping", "home"]);
    await user.keyboard("{Tab}");
    expect(box).toHaveValue("Milk #shopping ");
  });

  it("draws tag chips, removable, and adds the tags", async () => {
    parseQuickLineMock.mockImplementation(({ skip = [] }: { skip?: string[] }) => Promise.resolve(skip.includes("tag")
      ? makeRichLine({ title: "Milk #shopping", ready: true })
      : makeRichLine({ title: "Milk", ready: true, tags: ["shopping"] })));
    const user = userEvent.setup();
    render(<QuickAdd onAdded={onAdded} />);
    await user.type(screen.getByLabelText("New task"), "Milk #shopping");
    expect(await screen.findByText("#shopping")).toHaveClass("quick-chip--read");
    await user.click(screen.getByRole("button", { name: "Add" }));
    await waitFor(() => expect(createTaskMock).toHaveBeenCalledWith({ title: "Milk", tags: ["shopping"] }));
  });
});
