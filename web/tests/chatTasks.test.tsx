import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { ApiError } from "../src/api/client";
import { ChatContext, type ChatShared } from "../src/components/chat/chatContext";
import { answerWords, movedWords, pickedDue } from "../src/components/chat/reminderActions";
import { MessageRow } from "../src/components/MessageRow";
import { parseTaskCards } from "../src/lib/taskCards";
import { makeMessage } from "./fixtures";
import { makeRow } from "./taskFixtures";

const listTasksMock = vi.fn();
const completeMock = vi.fn();
const reopenMock = vi.fn();
const failMock = vi.fn();
const updateMock = vi.fn();
vi.mock("../src/api/tasks", () => ({
  listTasks: (...a: unknown[]) => listTasksMock(...a),
  completeTask: (...a: unknown[]) => completeMock(...a),
  reopenTask: (...a: unknown[]) => reopenMock(...a),
  failTask: (...a: unknown[]) => failMock(...a),
  updateTask: (...a: unknown[]) => updateMock(...a),
}));
const answerMock = vi.fn();
vi.mock("../src/api/threads", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../src/api/threads")>()),
  answerReminder: (...a: unknown[]) => answerMock(...a),
}));
vi.mock("../src/hooks/useLiveStore", () => ({
  useLiveState: () => ({ bots: {}, boardVersion: { tasks: 0, money: 0 }, routineVersion: { proposals: 0 } }),
}));

const PROJECTS = [{ id: "p1", name: "Casa Nueva" }];

function renderRow(node: ReactNode, shared: Partial<ChatShared> = {}) {
  return render(
    <MemoryRouter>
      <ChatContext.Provider value={{ projects: PROJECTS, ...shared }}>
        <ul>{node}</ul>
      </ChatContext.Provider>
    </MemoryRouter>,
  );
}

const cardsMessage = (body: unknown) => makeMessage({
  id: "m-c", role: "activity", kind: "task_cards", author_bot_id: "bot-1",
  body: typeof body === "string" ? body : JSON.stringify(body),
});

const reminder = (taskId: string | null, answer: Record<string, unknown> = {}) => makeMessage({
  id: "m-rem", role: "bot", kind: "report", author_bot_id: "bot-1",
  body: JSON.stringify({ source: "reminder", headline: "Reminder: Fix the sink", text: "Quick reminder: Fix the sink is due today.",
    tainted: false, task_id: taskId, ...answer }),
});

const row = (message: ReturnType<typeof makeMessage>) => (
  <MessageRow message={message} runStart fallbackName="Gela" team={[]} />
);

beforeEach(() => {
  [listTasksMock, completeMock, reopenMock, failMock, updateMock, answerMock].forEach((mock) => mock.mockReset());
  answerMock.mockResolvedValue({});
  try { window.localStorage.clear(); } catch { /* no storage */ }
});
afterEach(cleanup);

describe("parseTaskCards", () => {
  it("reads the server's body and refuses anything else", () => {
    expect(parseTaskCards(JSON.stringify({ task_ids: ["a", 3, "b"], verb: "listed", more: 2 })))
      .toEqual({ taskIds: ["a", "b"], verb: "listed", more: 2 });
    expect(parseTaskCards(JSON.stringify({ task_ids: ["a"], verb: "odd", more: -1 })))
      .toEqual({ taskIds: ["a"], verb: "tasks", more: 0 });
    expect(parseTaskCards(JSON.stringify({ task_ids: [] }))).toBeNull();
    expect(parseTaskCards("not json")).toBeNull();
    expect(parseTaskCards("null")).toBeNull();
  });
});

describe("task cards in the chat", () => {
  it("draws each task as a row with its due, project and web mark, in the order the server gave", async () => {
    listTasksMock.mockResolvedValue([
      makeRow({ id: "t1", title: "Fix the sink", project_id: "p1", priority: "urgent" }),
      makeRow({ id: "t2", title: "Pay the deposit", due_date: null, tainted: true }),
    ]);
    renderRow(row(cardsMessage({ task_ids: ["t1", "t2"], verb: "listed", more: 3 })));
    expect(await screen.findByText("Fix the sink")).toBeInTheDocument();
    expect(listTasksMock).toHaveBeenCalledWith({ ids: ["t1", "t2"] });
    expect(screen.getByRole("region", { name: "Your tasks" })).toBeInTheDocument();
    expect(screen.getByText("Casa Nueva")).toBeInTheDocument();
    expect(screen.getByText("Urgent")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "From web content" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "and 3 more on the Board" })).toHaveAttribute("href", "/board");
  });

  it("a tick finishes an open task, a done one opens again, and a title opens the drawer", async () => {
    const openTask = vi.fn();
    listTasksMock.mockResolvedValue([makeRow({ id: "t1", title: "Fix the sink" }),
      makeRow({ id: "t2", title: "Old one", status: "done" })]);
    completeMock.mockResolvedValue({});
    reopenMock.mockResolvedValue({});
    renderRow(row(cardsMessage({ task_ids: ["t1", "t2"], verb: "added", more: 0 })), { openTask });
    await userEvent.click(await screen.findByRole("button", { name: "Mark “Fix the sink” done" }));
    expect(completeMock).toHaveBeenCalledWith("t1");
    await userEvent.click(screen.getByRole("button", { name: "Open “Old one” again" }));
    expect(reopenMock).toHaveBeenCalledWith("t2");
    await userEvent.click(screen.getByRole("button", { name: "Fix the sink" }));
    expect(openTask).toHaveBeenCalledWith("t1");
    expect(screen.getByRole("region", { name: "Added 2 tasks" })).toBeInTheDocument();
  });

  it("says when the tasks are gone, and a failed tick says why", async () => {
    listTasksMock.mockResolvedValueOnce([]);
    const { unmount } = renderRow(row(cardsMessage({ task_ids: ["t9"], verb: "added", more: 0 })));
    expect(await screen.findByText("These tasks are gone.")).toBeInTheDocument();
    unmount();
    listTasksMock.mockResolvedValue([makeRow({ id: "t1", title: "Fix the sink" })]);
    completeMock.mockRejectedValue(new ApiError(500, "Could not save."));
    renderRow(row(cardsMessage({ task_ids: ["t1"], verb: "added", more: 0 })));
    await userEvent.click(await screen.findByRole("button", { name: "Mark “Fix the sink” done" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });

  it("shows the first five tasks and folds the rest behind Show more", async () => {
    const ids = ["t1", "t2", "t3", "t4", "t5", "t6", "t7"];
    listTasksMock.mockResolvedValue(ids.map((id) => makeRow({ id, title: `Task ${id}` })));
    renderRow(row(cardsMessage({ task_ids: ids, verb: "listed", more: 0 })));
    expect(await screen.findByText("Task t5")).toBeInTheDocument();
    expect(screen.queryByText("Task t6")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Show 2 more" }));
    expect(screen.getByText("Task t7")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Show less" }));
    expect(screen.queryByText("Task t6")).not.toBeInTheDocument();
  });

  it("five tasks or fewer need no toggle", async () => {
    const ids = ["t1", "t2", "t3", "t4", "t5"];
    listTasksMock.mockResolvedValue(ids.map((id) => makeRow({ id, title: `Task ${id}` })));
    renderRow(row(cardsMessage({ task_ids: ids, verb: "listed", more: 0 })));
    expect(await screen.findByText("Task t5")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Show/ })).not.toBeInTheDocument();
  });

  it("an unreadable body draws nothing", () => {
    const { container } = renderRow(row(cardsMessage("{}")));
    expect(container.querySelector("li")).toBeNull();
  });
});

describe("#Project chips in your own bubble", () => {
  it("draws a known #Name as a chip that opens the project, and leaves an unknown one as text", () => {
    renderRow(row(makeMessage({ id: "m-u", role: "user", body: "what is left in #casa nueva and #Garden?" })));
    const chip = screen.getByRole("link", { name: "Project Casa Nueva" });
    expect(chip).toHaveAttribute("href", "/board/projects/p1");
    expect(screen.getByText(/#Garden/)).toBeInTheDocument();
  });
});

describe("the reminder card", () => {
  const task = makeRow({ id: "t1", title: "Fix the sink", project_id: "p1" });

  it("is the bot's own words in a bubble, a quiet Reminder footer and four small chips; Done says so", async () => {
    listTasksMock.mockResolvedValue([task]);
    completeMock.mockResolvedValue({});
    renderRow(<MessageRow message={reminder("t1")} runStart fallbackName="Gela" team={[]} />);
    expect(await screen.findByText("Quick reminder: Fix the sink is due today.")).toBeInTheDocument();
    expect(screen.getByText("🔔 Reminder")).toBeInTheDocument();
    const chips = await screen.findByRole("group", { name: "Reminder actions" });
    expect(within(chips).getAllByRole("button").map((b) => b.textContent)).toEqual(["Done", "Failed", "Reschedule", "Skip"]);
    expect(within(chips).getByRole("button", { name: "Done" })).toHaveClass("reminder-chip");
    await userEvent.click(screen.getByRole("button", { name: "Done" }));
    expect(completeMock).toHaveBeenCalledWith("t1");
    expect(await screen.findByRole("status")).toHaveTextContent("✓ Done");
    expect(screen.queryByRole("group", { name: "Reminder actions" })).toBeNull();
    await waitFor(() => expect(answerMock).toHaveBeenCalledWith("t-1", "m-rem", "done", null));
  });

  it("Failed marks it failed, and Skip is stored on the server and changes no task", async () => {
    listTasksMock.mockResolvedValue([task]);
    failMock.mockResolvedValue({});
    const { unmount } = renderRow(row(reminder("t1")));
    await userEvent.click(await screen.findByRole("button", { name: "Failed" }));
    expect(failMock).toHaveBeenCalledWith("t1");
    expect(await screen.findByRole("status")).toHaveTextContent("Marked failed");
    await waitFor(() => expect(answerMock).toHaveBeenCalledWith("t-1", "m-rem", "failed", null));
    unmount();
    renderRow(row(reminder("t1")));
    await userEvent.click(await screen.findByRole("button", { name: "Skip" }));
    expect(answerMock).toHaveBeenLastCalledWith("t-1", "m-rem", "skipped", null);
    expect(await screen.findByRole("status")).toHaveTextContent("Skipped");
    expect(completeMock).not.toHaveBeenCalled();
    expect(updateMock).not.toHaveBeenCalled();
  });

  it("draws the server's stored answer instead of the buttons, on any screen", async () => {
    listTasksMock.mockResolvedValue([task]);
    const { unmount } = renderRow(row(reminder("t1", { answer: "skipped" })));
    expect(await screen.findByRole("status")).toHaveTextContent("Skipped");
    expect(screen.queryByRole("group", { name: "Reminder actions" })).toBeNull();
    unmount();
    const moved = renderRow(row(reminder("t1", { answer: "rescheduled", answer_due: "2026-10-29T10:00" })));
    expect(await screen.findByRole("status")).toHaveTextContent("Moved to Thu 29 Oct 10:00");
    moved.unmount();
    renderRow(row(reminder("t1", { answer: "rescheduled", answer_due: null })));
    expect(await screen.findByRole("status")).toHaveTextContent("Now has no date");
  });

  it("a Skip the server refused keeps the buttons and says why", async () => {
    listTasksMock.mockResolvedValue([task]);
    answerMock.mockRejectedValue(new ApiError(500, "The server is away"));
    renderRow(row(reminder("t1")));
    await userEvent.click(await screen.findByRole("button", { name: "Skip" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The server is away");
    expect(screen.getByRole("group", { name: "Reminder actions" })).toBeInTheDocument();
  });

  it("a deleted task says it is gone, before or after a button", async () => {
    listTasksMock.mockResolvedValue([]);
    const { unmount } = renderRow(row(reminder("t1")));
    expect(await screen.findByRole("status")).toHaveTextContent("This task is gone.");
    unmount();
    listTasksMock.mockResolvedValue([task]);
    completeMock.mockRejectedValue(new ApiError(404, "No open task with that id"));
    renderRow(row(reminder("t1")));
    await userEvent.click(await screen.findByRole("button", { name: "Done" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("This task is gone."));
  });

  it("a done task says Done after a reload, and a reminder with no task stays a plain report", async () => {
    listTasksMock.mockResolvedValue([{ ...task, status: "done" }]);
    const { unmount } = renderRow(row(reminder("t1")));
    expect(await screen.findByRole("status")).toHaveTextContent("✓ Done");
    unmount();
    renderRow(row(reminder(null)));
    expect(screen.getByRole("article", { name: "Report: Reminder: Fix the sink" })).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "Reminder actions" })).toBeNull();
  });

  it("the footer opens the task in the drawer", async () => {
    listTasksMock.mockResolvedValue([task]);
    const openTask = vi.fn();
    renderRow(row(reminder("t1")), { openTask });
    await userEvent.click(await screen.findByRole("button", { name: "Open task Fix the sink" }));
    expect(openTask).toHaveBeenCalledWith("t1");
  });
});

describe("reschedule words", () => {
  const task = makeRow({ due_date: "2026-10-16T09:00:00+02:00" });

  it("keeps the task's own time when the pick has none, and says where it moved", () => {
    expect(pickedDue(task, { day: "2026-10-29", time: null })).toBe("2026-10-29T09:00");
    expect(pickedDue(task, { day: "2026-10-29", time: "10:30" })).toBe("2026-10-29T10:30");
    expect(pickedDue(makeRow({ due_date: null }), { day: "2026-10-29", time: null })).toBe("2026-10-29");
    expect(pickedDue(task, { day: null, time: null })).toBeNull();
    expect(movedWords(task, { day: "2026-10-29", time: "10:00" })).toBe("Moved to Thu 29 Oct 10:00");
    expect(movedWords(task, { day: null, time: null })).toBe("Now has no date");
  });

  it("says a stored answer in the card's words", () => {
    expect(answerWords("done", null)).toBe("✓ Done");
    expect(answerWords("failed", null)).toBe("Marked failed");
    expect(answerWords("skipped", null)).toBe("Skipped");
    expect(answerWords("rescheduled", "2026-10-29")).toBe("Moved to Thu 29 Oct");
    expect(answerWords("rescheduled", null)).toBe("Now has no date");
    expect(answerWords(null, null)).toBeNull();
  });
});
