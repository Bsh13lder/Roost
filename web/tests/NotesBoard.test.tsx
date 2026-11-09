import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import NotesBoard from "../src/components/notes/NotesBoard";
import type { NoteSummaryOut } from "../src/api/types";

const listNotesMock = vi.fn();
const createNoteMock = vi.fn();
const keepNoteMock = vi.fn();
vi.mock("../src/api/notes", () => ({
  listNotes: (...a: unknown[]) => listNotesMock(...a),
  createNote: (...a: unknown[]) => createNoteMock(...a),
  keepNote: (...a: unknown[]) => keepNoteMock(...a),
}));
vi.mock("../src/components/notes/NoteEditor", () => ({
  NoteEditor: ({ noteId, onClose }: { noteId: string; onClose: () => void }) => (
    <div><p>editing {noteId}</p><button type="button" onClick={onClose}>close editor</button></div>
  ),
}));
let live = { bots: {}, boardVersion: { tasks: 0, money: 0, notes: 0 } };
vi.mock("../src/hooks/useLiveStore", () => ({ useLiveState: () => live }));

function summary(overrides: Partial<NoteSummaryOut> = {}): NoteSummaryOut {
  return {
    id: "n1", title: "Ana", tags: ["people"], snippet: "Birthday 3 May, likes orchids", pinned: false, revision: 1,
    created_at: "2026-10-14T08:00:00Z", updated_at: "2026-10-14T08:00:00Z", created_by_bot: "b1", tainted: false,
    project_id: null, ...overrides,
  };
}

beforeEach(() => {
  live = { bots: {}, boardVersion: { tasks: 0, money: 0, notes: 0 } };
  for (const mock of [listNotesMock, createNoteMock, keepNoteMock]) mock.mockReset();
  listNotesMock.mockResolvedValue([summary(), summary({ id: "n2", title: "Recipe", tags: [], snippet: "bake", tainted: true })]);
});
afterEach(() => cleanup());

const rowOf = async (title: string) => (await screen.findByText(title)).closest("li") as HTMLElement;

describe("NotesBoard", () => {
  it("lists notes with their snippet and tags, and marks web content with Keep", async () => {
    keepNoteMock.mockResolvedValue({});
    const user = userEvent.setup();
    render(<NotesBoard />);
    const ana = await rowOf("Ana");
    expect(within(ana).getByText("Birthday 3 May, likes orchids")).toBeInTheDocument();
    expect(within(ana).getByText("#people")).toBeInTheDocument();
    expect(within(ana).queryByRole("button", { name: /^Keep/ })).not.toBeInTheDocument();
    await user.click(within(await rowOf("Recipe")).getByRole("button", { name: "Keep Recipe as yours" }));
    expect(keepNoteMock).toHaveBeenCalledWith("n2");
    expect(listNotesMock).toHaveBeenCalledWith("");
  });

  it("searches when you submit the search box", async () => {
    const user = userEvent.setup();
    render(<NotesBoard />);
    await screen.findByText("Ana");
    listNotesMock.mockResolvedValue([]);
    await user.type(screen.getByRole("searchbox", { name: "Search notes" }), "orchids{Enter}");
    await waitFor(() => expect(listNotesMock).toHaveBeenLastCalledWith("orchids"));
    expect(await screen.findByText("No note matches “orchids”.")).toBeInTheDocument();
  });

  it("opens a note in the editor and comes back to a fresh list", async () => {
    const user = userEvent.setup();
    render(<NotesBoard />);
    await user.click(within(await rowOf("Ana")).getByRole("button", { name: /Ana/ }));
    expect(screen.getByText("editing n1")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "close editor" }));
    expect(await screen.findByText("Ana")).toBeInTheDocument();
    await waitFor(() => expect(listNotesMock).toHaveBeenCalledTimes(2));
  });

  it("New note creates one and opens it", async () => {
    createNoteMock.mockResolvedValue({ id: "n9" });
    const user = userEvent.setup();
    render(<NotesBoard />);
    await user.click(await screen.findByRole("button", { name: "New note" }));
    expect(createNoteMock).toHaveBeenCalledWith({ title: "Untitled note", content: "" });
    expect(await screen.findByText("editing n9")).toBeInTheDocument();
  });

  it("shows a snippet as plain words, not markdown", async () => {
    listNotesMock.mockResolvedValue([summary({ snippet: "# Ana **Birthday** see [[Garden]]" })]);
    render(<NotesBoard />);
    expect(within(await rowOf("Ana")).getByText("Ana Birthday see Garden")).toBeInTheDocument();
  });

  it("hides the search while a note is open", async () => {
    const user = userEvent.setup();
    render(<NotesBoard />);
    await user.click(within(await rowOf("Ana")).getByRole("button", { name: /Ana/ }));
    expect(screen.queryByRole("searchbox", { name: "Search notes" })).not.toBeInTheDocument();
  });

  it("clearing the search box lists every note again", async () => {
    const user = userEvent.setup();
    render(<NotesBoard />);
    const box = await screen.findByRole("searchbox", { name: "Search notes" });
    await user.type(box, "orchids{Enter}");
    await waitFor(() => expect(listNotesMock).toHaveBeenLastCalledWith("orchids"));
    await user.clear(box);
    await waitFor(() => expect(listNotesMock).toHaveBeenLastCalledWith(""));
  });

  it("reloads when a notes_changed frame arrives", async () => {
    const { rerender } = render(<NotesBoard />);
    await screen.findByText("Ana");
    live = { bots: {}, boardVersion: { tasks: 0, money: 0, notes: 1 } };
    rerender(<NotesBoard />);
    await waitFor(() => expect(listNotesMock).toHaveBeenCalledTimes(2));
  });
});

describe("NotesBoard in a project", () => {
  it("lists and writes only that project's notes", async () => {
    createNoteMock.mockResolvedValue({ id: "n9" });
    const user = userEvent.setup();
    render(<NotesBoard projectId="p1" />);
    await screen.findByText("Ana");
    expect(listNotesMock).toHaveBeenCalledWith("", { projectId: "p1" });
    await user.click(screen.getByRole("button", { name: "New note" }));
    expect(createNoteMock).toHaveBeenCalledWith({ title: "Untitled note", content: "", project_id: "p1" });
    expect(await screen.findByText("editing n9")).toBeInTheDocument();
  });

  it("searches within the project", async () => {
    const user = userEvent.setup();
    render(<NotesBoard projectId="p1" />);
    await screen.findByText("Ana");
    await user.type(screen.getByRole("searchbox", { name: "Search notes" }), "orchids{Enter}");
    await waitFor(() => expect(listNotesMock).toHaveBeenLastCalledWith("orchids", { projectId: "p1" }));
  });
});
