import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ExpenseLine } from "../src/components/board/ExpenseLine";
import { FULL_EXPENSE_LINE, makeExpense, makeExpenseLine } from "./moneyFixtures";

const parseMock = vi.fn();
const createMock = vi.fn();
const listProjectsMock = vi.fn();
vi.mock("../src/api/money", () => ({
  parseExpenseLine: (...a: unknown[]) => parseMock(...a),
  createExpense: (...a: unknown[]) => createMock(...a),
}));
vi.mock("../src/api/projects", () => ({ listProjects: (...a: unknown[]) => listProjectsMock(...a) }));
vi.mock("../src/hooks/useLiveStore", () => ({ useLiveState: () => ({ bots: {}, boardVersion: { tasks: 0, money: 0 } }) }));

const TEXT = "€12 lunch /Trip yesterday vendor:Mercadona *";
const onAdded = vi.fn();

beforeEach(() => {
  parseMock.mockReset().mockImplementation(({ text }: { text: string }) =>
    Promise.resolve(text === TEXT ? FULL_EXPENSE_LINE : makeExpenseLine({ note: text })));
  createMock.mockReset().mockResolvedValue(makeExpense());
  listProjectsMock.mockReset().mockResolvedValue([
    { id: "p1", name: "Casa Nueva", status: "active" }, { id: "p2", name: "Old trip", status: "archived" },
    { id: "pg", name: "General", status: "active" },
  ]);
  onAdded.mockReset();
});
afterEach(() => cleanup());

const input = () => screen.getByLabelText("New expense");

describe("the expense line", () => {
  it("sits in the quick box with the € glyph, the ? help and the new placeholder", () => {
    render(<ExpenseLine onAdded={onAdded} />);
    const box = screen.getByRole("group", { name: "Add an expense" });
    expect(box.querySelector(".quick-box__glyph")).toHaveTextContent("€");
    expect(input()).toHaveAttribute("placeholder",
      "Add an expense… try “€12 lunch /Trip yesterday vendor:Mercadona *”");
  });

  it("shows amount, project, day, vendor and star chips from the server", async () => {
    render(<ExpenseLine onAdded={onAdded} />);
    await userEvent.setup().type(input(), TEXT, { delay: null });
    const chips = await screen.findByText("€12.00");
    const reading = chips.closest(".quick-add__reading") as HTMLElement;
    for (const label of ["€12.00", "/Trip", "Tue 20 Oct", "at Mercadona", "Starred"]) {
      expect(within(reading).getByText(label)).toBeInTheDocument();
    }
  });

  it("adds exactly the reading", async () => {
    const user = userEvent.setup();
    render(<ExpenseLine onAdded={onAdded} />);
    await user.type(input(), `${TEXT}{Enter}`, { delay: null });
    await waitFor(() => expect(createMock).toHaveBeenCalled());
    expect(createMock).toHaveBeenCalledWith({
      amount: "12.00", currency: "EUR", project_id: "p-trip", note: "lunch", spent_at: "2026-10-20",
      vendor: "Mercadona", starred: true,
    });
    await waitFor(() => expect(onAdded).toHaveBeenCalled());
    expect(input()).toHaveValue("");
  });

  it("a project's page passes its project to the server and to the add", async () => {
    parseMock.mockResolvedValue(makeExpenseLine({ note: "tiles", amount: "40.00", ready: true }));
    const user = userEvent.setup();
    render(<ExpenseLine projectId="p9" onAdded={onAdded} />);
    await user.type(input(), "€40 tiles{Enter}", { delay: null });
    await waitFor(() => expect(createMock).toHaveBeenCalled());
    expect(parseMock).toHaveBeenCalledWith(expect.objectContaining({ project_id: "p9" }));
    expect(createMock).toHaveBeenCalledWith(expect.objectContaining({ project_id: "p9", amount: "40.00" }));
  });

  it("/ suggests every project, not only this month's", async () => {
    const user = userEvent.setup();
    render(<ExpenseLine onAdded={onAdded} />);
    await user.type(input(), "€5 tea /", { delay: null });
    const list = await screen.findByRole("listbox", { name: "Suggestions" });
    expect(within(list).getAllByRole("option").map((option) => option.textContent)).toEqual(["Casa Nueva", "Old trip"]);
    await user.click(within(list).getByRole("option", { name: "Old trip" }));
    expect(input()).toHaveValue("€5 tea /Old trip ");
  });

  it("a project question blocks Enter", async () => {
    parseMock.mockResolvedValue(makeExpenseLine({
      note: "x", amount: "5.00", project_words: "/Tri", ready: false,
      project_question: "No project is called “Tri”. Did you mean Trip?",
    }));
    const user = userEvent.setup();
    render(<ExpenseLine onAdded={onAdded} />);
    await user.type(input(), "€5 x /Tri{Enter}", { delay: null });
    expect(await screen.findByText("No project is called “Tri”. Did you mean Trip?", { selector: ".quick-add__ask" }))
      .toBeInTheDocument();
    expect(createMock).not.toHaveBeenCalled();
  });

  it("without an amount it asks for one", async () => {
    const user = userEvent.setup();
    render(<ExpenseLine onAdded={onAdded} />);
    await user.type(input(), "lunch{Enter}", { delay: null });
    expect(await screen.findByText("Add an amount, like €12.")).toBeInTheDocument();
    expect(createMock).not.toHaveBeenCalled();
  });

  it("shows worked maths and money in", async () => {
    parseMock.mockResolvedValue(makeExpenseLine({
      note: "paint", amount: "62.00", amount_math: "2×31", amount_words: "€2x31", ready: true,
    }));
    const user = userEvent.setup();
    const { rerender } = render(<ExpenseLine onAdded={onAdded} />);
    await user.type(input(), "€2x31 paint", { delay: null });
    expect(await screen.findByText("€62.00 = 2×31")).toBeInTheDocument();
    parseMock.mockResolvedValue(makeExpenseLine({ note: "salary", amount: "500.00", income: true, ready: true }));
    rerender(<ExpenseLine key="again" onAdded={onAdded} />);
    await userEvent.setup().type(input(), "+€500 salary", { delay: null });
    expect(await screen.findByText("Money in €500.00")).toBeInTheDocument();
  });

  it("removing a chip asks the server to leave its words in the note", async () => {
    const user = userEvent.setup();
    render(<ExpenseLine onAdded={onAdded} />);
    await user.type(input(), TEXT, { delay: null });
    await user.click(await screen.findByRole("button", { name: "Remove /Trip" }));
    await waitFor(() => expect(parseMock).toHaveBeenLastCalledWith(expect.objectContaining({ skip: ["project"] })));
  });

  it("has the ? help with the expense tokens", async () => {
    const user = userEvent.setup();
    render(<ExpenseLine onAdded={onAdded} />);
    await user.click(screen.getByRole("button", { name: "Quick line help" }));
    const help = await screen.findByRole("dialog", { name: "Quick line help" });
    expect(within(help).getByText("Makes it a repeating expense")).toBeInTheDocument();
    expect(within(help).getByText("vendor:")).toBeInTheDocument();
  });

  it("shows the gateway's refusal when the add fails", async () => {
    const { ApiError } = await import("../src/api/client");
    createMock.mockRejectedValue(new ApiError(422, "“Trip” is archived; unarchive it first."));
    const user = userEvent.setup();
    render(<ExpenseLine onAdded={onAdded} />);
    await user.type(input(), `${TEXT}{Enter}`, { delay: null });
    expect(await screen.findByText("“Trip” is archived; unarchive it first.", { selector: ".quick-add__ask" }))
      .toBeInTheDocument();
    expect(onAdded).not.toHaveBeenCalled();
  });

  it("sends default_day and shows the day chip", async () => {
    const user = userEvent.setup();
    parseMock.mockResolvedValue(makeExpenseLine({ note: "lunch", amount: "12.00", ready: true, spent_at: "2026-10-21" }));
    render(<ExpenseLine defaultDay="2026-10-21" onAdded={onAdded} />);
    expect(screen.getByText("On Wed 21 Oct")).toBeInTheDocument(); // first, before anything is typed
    await user.type(input(), "€12 lunch", { delay: null });
    await waitFor(() => expect(parseMock).toHaveBeenCalledWith(expect.objectContaining({ default_day: "2026-10-21" })));
    expect(screen.getByText("On Wed 21 Oct")).toBeInTheDocument();
    await user.type(input(), "{Enter}", { delay: null });
    await waitFor(() => expect(createMock).toHaveBeenCalledWith(expect.objectContaining({ spent_at: "2026-10-21" })));
    expect(parseMock).toHaveBeenLastCalledWith(expect.objectContaining({ default_day: "2026-10-21" }));
  });

  it("a day typed in the line replaces the badge", async () => {
    parseMock.mockResolvedValue(makeExpenseLine({ note: "lunch", amount: "12.00", ready: true, spent_at: "2026-10-20",
      spent_text: "Tue 20 Oct", day_words: "yesterday" }));
    render(<ExpenseLine defaultDay="2026-10-21" onAdded={onAdded} />);
    await userEvent.setup().type(input(), "€12 lunch yesterday", { delay: null });
    expect(await screen.findByText("Tue 20 Oct")).toBeInTheDocument();
    expect(screen.queryByText("On Wed 21 Oct")).not.toBeInTheDocument();
  });
});

describe("the expense line in a task's drawer (project and task fixed)", () => {
  const fixed = { projectId: "p1", taskId: "t1", label: "Fix the sink" };

  it("never reads a /project: the words stay in the note and no project list is offered", async () => {
    parseMock.mockResolvedValue(makeExpenseLine({ note: "tiles /Trip", amount: "40.00", ready: true }));
    const user = userEvent.setup();
    render(<ExpenseLine fixed={fixed} onAdded={onAdded} />);
    await user.type(input(), "€40 tiles /Trip", { delay: null });
    await waitFor(() => expect(parseMock).toHaveBeenCalledWith(expect.objectContaining({ project_id: "p1", skip: ["project"] })));
    expect(screen.queryByRole("listbox", { name: "Suggestions" })).not.toBeInTheDocument();
    expect(listProjectsMock).not.toHaveBeenCalled();
  });

  it("shows the task it is for, and files the expense under it in its project", async () => {
    parseMock.mockResolvedValue(makeExpenseLine({ note: "tiles", amount: "40.00", ready: true, project: FULL_EXPENSE_LINE.project }));
    const user = userEvent.setup();
    render(<ExpenseLine fixed={{ ...fixed, stepId: "s-2" }} onAdded={onAdded} />);
    expect(screen.getByText("For Fix the sink", { selector: ".quick-chip" })).toBeInTheDocument();
    await user.type(input(), "€40 tiles{Enter}", { delay: null });
    await waitFor(() => expect(createMock).toHaveBeenCalled());
    expect(createMock).toHaveBeenCalledWith(expect.objectContaining({ project_id: "p1", task_id: "t1", step_id: "s-2", amount: "40.00" }));
  });

  it("a task in no project files the expense under the task alone", async () => {
    parseMock.mockResolvedValue(makeExpenseLine({ note: "tea", amount: "3.00", ready: true }));
    const user = userEvent.setup();
    render(<ExpenseLine fixed={{ ...fixed, projectId: null }} onAdded={onAdded} />);
    await user.type(input(), "€3 tea{Enter}", { delay: null });
    await waitFor(() => expect(createMock).toHaveBeenCalled());
    const sent = createMock.mock.calls[0][0] as Record<string, unknown>;
    expect(sent).toMatchObject({ task_id: "t1", amount: "3.00" });
    expect(sent).not.toHaveProperty("project_id");
    expect(parseMock).toHaveBeenCalledWith(expect.not.objectContaining({ project_id: expect.anything() }));
  });
});
