import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QuickAdd } from "../src/components/tasks/QuickAdd";
import { keepWords, stillTyped } from "../src/components/tasks/quickKept";
import { makeRichLine } from "./quickRichFixtures";
import { makeTask } from "./taskFixtures";

const parseQuickLineMock = vi.fn();
const createTaskMock = vi.fn();
vi.mock("../src/api/projects", () => ({ listProjects: () => Promise.resolve([]) }));
vi.mock("../src/hooks/useLiveStore", () => ({ useLiveState: () => ({ bots: {}, boardVersion: { money: 0, tasks: 0 } }) }));
vi.mock("../src/api/tasks", () => ({
  parseQuickLine: (...a: unknown[]) => parseQuickLineMock(...a),
  createTask: (...a: unknown[]) => createTaskMock(...a),
  listTasks: () => Promise.resolve([]),
}));

// A stand-in for the server's rule: "tomorrow" and "friday" are dates unless they are kept words; a kept
// word stays in the title as typed.
const WORDS = ["tomorrow", "friday"];
function server({ text, keep = [] }: { text: string; keep?: string[] }) {
  const typed = text.split(/\s+/).filter(Boolean);
  const date = typed.find((word) => WORDS.includes(word.toLowerCase()) && !keep.some((k) => k.toLowerCase() === word.toLowerCase()));
  const title = typed.filter((word) => word !== date).join(" ");
  return Promise.resolve(makeRichLine({
    title, ready: Boolean(title), due_date: date ? "2026-10-21" : null, due_text: date ? "Wed 21 Oct" : null,
    matches: date ? { date: [date] } : {},
  }));
}

beforeEach(() => {
  parseQuickLineMock.mockReset().mockImplementation(server);
  createTaskMock.mockReset().mockResolvedValue(makeTask());
});
afterEach(() => cleanup());

describe("cancelling a match", () => {
  it("puts the word back in the title at once and keeps it back while typing on", async () => {
    const user = userEvent.setup();
    render(<QuickAdd onAdded={vi.fn()} />);
    const box = screen.getByLabelText("New task");
    await user.type(box, "Call Ana tomorrow");
    await user.click(await screen.findByRole("button", { name: "Remove Wed 21 Oct" }));
    expect(screen.queryByText("Wed 21 Oct")).not.toBeInTheDocument(); // gone before the server answers
    await waitFor(() => expect(parseQuickLineMock).toHaveBeenLastCalledWith({ text: "Call Ana tomorrow", keep: ["tomorrow"] }));
    await user.type(box, " at the shop");
    await waitFor(() => expect(parseQuickLineMock).toHaveBeenLastCalledWith(
      { text: "Call Ana tomorrow at the shop", keep: ["tomorrow"] }));
    expect(screen.queryByText("Wed 21 Oct")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Add" }));
    await waitFor(() => expect(createTaskMock).toHaveBeenCalledWith({ title: "Call Ana tomorrow at the shop" }));
  });

  it("reads a new date word, and lets go of a deleted one", async () => {
    const user = userEvent.setup();
    render(<QuickAdd onAdded={vi.fn()} />);
    const box = screen.getByLabelText("New task");
    await user.type(box, "Call tomorrow");
    await user.click(await screen.findByRole("button", { name: "Remove Wed 21 Oct" }));
    await user.type(box, " friday");
    expect(await screen.findByText("Wed 21 Oct")).toBeInTheDocument(); // friday is a new word: read
    await user.clear(box);
    await user.type(box, "Call tomorrow");
    expect(await screen.findByText("Wed 21 Oct")).toBeInTheDocument(); // typed again from empty: read again
  });
});

describe("the kept words", () => {
  it("are added once and dropped when no longer typed", () => {
    expect(keepWords(["tomorrow"], ["Tomorrow", "at 9"])).toEqual(["tomorrow", "at 9"]);
    expect(stillTyped(["tomorrow", "at 9"], "Call TOMORROW")).toEqual(["tomorrow"]);
  });
});
