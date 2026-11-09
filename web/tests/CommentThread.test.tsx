import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CommentThread } from "../src/components/tasks/CommentThread";
import { ApiError } from "../src/api/client";
import { makeBot } from "./fixtures";
import { makeComment, makeTask } from "./taskFixtures";

const listCommentsMock = vi.fn();
const addCommentMock = vi.fn();
const editCommentMock = vi.fn();
const deleteCommentMock = vi.fn();
vi.mock("../src/api/comments", () => ({
  listComments: (...a: unknown[]) => listCommentsMock(...a),
  addComment: (...a: unknown[]) => addCommentMock(...a),
  editComment: (...a: unknown[]) => editCommentMock(...a),
  deleteComment: (...a: unknown[]) => deleteCommentMock(...a),
}));
let live = { bots: { "bot-1": makeBot({ id: "bot-1", name: "Helper" }) }, boardVersion: { tasks: 0, money: 0 } };
vi.mock("../src/hooks/useLiveStore", () => ({ useLiveState: () => live }));

const task = makeTask();
const HOSTILE = '<img src=x onerror="alert(1)"><script>steal()</script> Buy it at shop.example';
const itemOf = (found: string | HTMLElement) =>
  (typeof found === "string" ? screen.getByText(found) : found).closest("li") as HTMLElement;

beforeEach(() => {
  live = { bots: { "bot-1": makeBot({ id: "bot-1", name: "Helper" }) }, boardVersion: { tasks: 0, money: 0 } };
  for (const mock of [listCommentsMock, addCommentMock, editCommentMock, deleteCommentMock]) mock.mockReset();
  listCommentsMock.mockResolvedValue([
    makeComment(),
    makeComment({ id: "c2", author: "bot-1", step_id: "s-1", body: "Size 15 mm", created_at: "2026-10-15T09:30:00+00:00" }),
    makeComment({ id: "c3", author: "bot-gone", body: "Old note", edited_at: "2026-10-15T10:00:00+00:00" }),
  ]);
  for (const mock of [addCommentMock, editCommentMock, deleteCommentMock]) mock.mockResolvedValue(makeComment());
});
afterEach(() => cleanup());

describe("the drawer's comments (redesign P3)", () => {
  it("lists the thread with each author, step and time, and Edit and Delete only on the user's own", async () => {
    render(<CommentThread task={task} />);
    const mine = itemOf(await screen.findByText("The plumber comes at 9"));
    expect(within(mine).getByText("You")).toBeInTheDocument();
    expect(within(mine).getByText("Thu 15 Oct, 10:00")).toBeInTheDocument();
    expect(within(mine).getByRole("button", { name: "Edit" })).toBeInTheDocument();
    const bots = itemOf("Size 15 mm");
    expect(within(bots).getByText("Helper")).toBeInTheDocument();
    expect(within(bots).getByText("on “Buy a washer”")).toBeInTheDocument();
    expect(within(bots).queryByRole("button", { name: "Edit" })).not.toBeInTheDocument();
    const old = itemOf("Old note");
    expect(within(old).getByText("A retired bot")).toBeInTheDocument();
    expect(within(old).getByText("edited")).toBeInTheDocument();
    expect(listCommentsMock).toHaveBeenCalledWith("t1");
  });

  it("shows a bot's web-made comment as plain text with its mark, and no Edit or Delete", async () => {
    listCommentsMock.mockResolvedValue([makeComment({ id: "c9", author: "bot-1", body: HOSTILE, tainted: true })]);
    const { container } = render(<CommentThread task={task} />);
    const item = itemOf(await screen.findByText(HOSTILE));
    expect(within(item).getByText("from web content")).toBeInTheDocument();
    expect(container.querySelector("img, script")).toBeNull();
    expect(within(item).queryByRole("button")).not.toBeInTheDocument();
  });

  it("comments on the whole task or on a step, with the button or Cmd+Enter", async () => {
    const user = userEvent.setup();
    render(<CommentThread task={task} />);
    await screen.findByText("The plumber comes at 9");
    await user.type(screen.getByLabelText("New comment"), "Called him");
    await user.click(screen.getByRole("button", { name: "Comment" }));
    expect(addCommentMock).toHaveBeenCalledWith("t1", { body: "Called him" });
    await waitFor(() => expect(screen.getByLabelText("New comment")).toHaveValue(""));
    await user.click(screen.getByRole("combobox", { name: "About" }));
    await user.click(await screen.findByRole("option", { name: "Fit it" }));
    await user.type(screen.getByLabelText("New comment"), "Needs a 15 mm key{Meta>}{Enter}{/Meta}");
    expect(addCommentMock).toHaveBeenLastCalledWith("t1", { body: "Needs a 15 mm key", step_id: "s-2" });
  });

  it("edits and deletes the user's own comment, and reloads", async () => {
    const user = userEvent.setup();
    render(<CommentThread task={task} />);
    const mine = itemOf(await screen.findByText("The plumber comes at 9"));
    await user.click(within(mine).getByRole("button", { name: "Edit" }));
    const box = screen.getByLabelText("Edit your comment");
    await user.clear(box);
    await user.type(box, "The plumber comes at 10");
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(editCommentMock).toHaveBeenCalledWith("c1", "The plumber comes at 10");
    await user.click(within(itemOf("The plumber comes at 9")).getByRole("button", { name: "Delete" }));
    expect(deleteCommentMock).toHaveBeenCalledWith("c1");
    await waitFor(() => expect(listCommentsMock).toHaveBeenCalledTimes(3));
  });

  it("says when there are none, and shows the server's reason when a comment is refused", async () => {
    listCommentsMock.mockResolvedValue([]);
    addCommentMock.mockRejectedValue(new ApiError(422, "A comment needs some words."));
    const user = userEvent.setup();
    render(<CommentThread task={makeTask({ steps: [] })} />);
    expect(await screen.findByText("No comments yet.")).toBeInTheDocument();
    expect(screen.queryByRole("combobox", { name: "About" })).not.toBeInTheDocument();
    await user.type(screen.getByLabelText("New comment"), "x");
    await user.click(screen.getByRole("button", { name: "Comment" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("A comment needs some words.");
  });
});
