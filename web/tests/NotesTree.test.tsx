import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import NotesTree from "../src/components/workspace/notes/NotesTree";
import type { DocumentOut, NoteSummaryOut } from "../src/api/types";
import { makeProject } from "./projectFixtures";

const listNotesMock = vi.fn();
const createNoteMock = vi.fn();
vi.mock("../src/api/notes", () => ({
  listNotes: (...a: unknown[]) => listNotesMock(...a), createNote: (...a: unknown[]) => createNoteMock(...a),
}));
const listDocumentsMock = vi.fn();
const getDocumentMock = vi.fn();
vi.mock("../src/api/documents", () => ({
  listDocuments: (...a: unknown[]) => listDocumentsMock(...a), getDocument: (...a: unknown[]) => getDocumentMock(...a),
}));
const listProjectsMock = vi.fn();
vi.mock("../src/api/projects", () => ({ listProjects: (...a: unknown[]) => listProjectsMock(...a) }));
vi.mock("../src/hooks/useLiveStore", () => ({
  useLiveState: () => ({ bots: {}, boardVersion: { tasks: 0, money: 0, notes: 0, documents: 0 } }),
}));
vi.mock("../src/components/notes/NoteEditor", () => ({
  NoteEditor: ({ noteId, onClose }: { noteId: string; onClose: () => void }) => (
    <div><p>Editing note {noteId}</p><button type="button" onClick={onClose}>Close note</button></div>
  ),
}));
vi.mock("../src/components/documents/DocumentOpen", () => ({
  DocumentOpen: ({ document, onBack }: { document: { id: string }; onBack: () => void }) => (
    <div><p>Open document {document.id}</p><button type="button" onClick={onBack}>Back to notes</button></div>
  ),
}));

const note = (overrides: Partial<NoteSummaryOut>): NoteSummaryOut => ({
  id: "n1", title: "Upgrades", tags: [], snippet: "", pinned: false, revision: 1, created_at: "2026-10-20T08:00:00Z",
  updated_at: "2026-10-20T08:00:00Z", created_by_bot: null, tainted: false, project_id: null, ...overrides,
});
const doc = (overrides: Partial<DocumentOut>): DocumentOut => ({
  id: "d1", kind: "sheet", title: "Numbers", pages: null, revision: 1, created_at: "2026-10-20T08:00:00Z",
  updated_at: "2026-10-20T08:00:00Z", created_by_bot: null, tainted: false, project_id: null, ...overrides,
});

function Where() {
  return <output aria-label="Address">{useLocation().search}</output>;
}

function tree(start = "/board?tab=notes", props: { openNote?: string | null; openDocument?: string | null } = {}) {
  return render(
    <MemoryRouter initialEntries={[start]}><NotesTree {...props} /><Where /></MemoryRouter>,
  );
}

const folder = (name: RegExp) => screen.getByRole("button", { name });
const address = () => screen.getByRole("status", { name: "Address" });

beforeEach(() => {
  listProjectsMock.mockReset().mockResolvedValue([makeProject({ id: "p1", name: "Club" }), makeProject({ id: "p2", name: "Empty" })]);
  listNotesMock.mockReset().mockResolvedValue([
    note({ id: "n1", title: "Upgrades", project_id: "p1" }), note({ id: "n2", title: "Web-page traffic", project_id: "p1" }),
    note({ id: "n3", title: "ToDo" }),
  ]);
  listDocumentsMock.mockReset().mockResolvedValue([doc({ id: "d1", title: "Beginning numbers", project_id: "p1" })]);
  createNoteMock.mockReset().mockResolvedValue(note({ id: "n9", title: "Untitled note" }));
  getDocumentMock.mockReset().mockResolvedValue({ ...doc({ id: "d1" }), payload: null });
});
afterEach(() => cleanup());

describe("the Workspace's Notes tree", () => {
  it("has one folder per project that holds something, then No project, each with its count", async () => {
    tree();
    expect(await screen.findByRole("button", { name: /^Club/ })).toHaveTextContent("3 files");
    expect(folder(/^No project/)).toHaveTextContent("1 file");
    expect(screen.queryByRole("button", { name: /^Empty/ })).toBeNull();
    expect(screen.getByRole("heading", { name: "Notes" })).toBeInTheDocument();
  });

  it("folders open and close, and list notes and documents with their type", async () => {
    tree();
    const club = await screen.findByRole("button", { name: /^Club/ });
    expect(club).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText("Upgrades")).toBeNull();
    await userEvent.click(club);
    expect(club).toHaveAttribute("aria-expanded", "true");
    const list = screen.getByRole("group", { name: "Club" });
    expect(within(list).getByRole("button", { name: "Note: Upgrades" })).toBeInTheDocument();
    expect(within(list).getByRole("button", { name: "Sheet: Beginning numbers" })).toBeInTheDocument();
    await userEvent.click(club);
    expect(screen.queryByText("Upgrades")).toBeNull();
  });

  it("the pill's words (?q=) filter by title and open every folder that matches", async () => {
    tree("/board?tab=notes&q=numb");
    expect(await screen.findByRole("button", { name: "Sheet: Beginning numbers" })).toBeInTheDocument();
    expect(screen.queryByText("Upgrades")).toBeNull();
    expect(screen.queryByRole("button", { name: /^No project/ })).toBeNull();
  });

  it("says so when nothing matches", async () => {
    tree("/board?tab=notes&q=zebra");
    expect(await screen.findByText("Nothing matches “zebra”.")).toBeInTheDocument();
  });

  it("a note opens in the note editor at ?note=, and closing goes back to the tree", async () => {
    const view = tree();
    await userEvent.click(await screen.findByRole("button", { name: /^No project/ }));
    await userEvent.click(screen.getByRole("button", { name: "Note: ToDo" }));
    expect(address()).toHaveTextContent("note=n3");
    view.unmount();
    tree("/board?tab=notes&note=n3", { openNote: "n3" });
    expect(screen.getByText("Editing note n3")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Close note" }));
    expect(address()).not.toHaveTextContent("note=");
  });

  it("a document opens in its editor at ?document=", async () => {
    tree("/board?tab=notes&document=d1", { openDocument: "d1" });
    expect(await screen.findByText("Open document d1")).toBeInTheDocument();
    expect(getDocumentMock).toHaveBeenCalledWith("d1");
  });

  it("New note makes one and opens it", async () => {
    tree();
    await userEvent.click(await screen.findByRole("button", { name: "New note" }));
    await waitFor(() => expect(createNoteMock).toHaveBeenCalledWith({ title: "Untitled note", content: "" }));
    await waitFor(() => expect(address()).toHaveTextContent("note=n9"));
  });

  it("says a failed load in words, with Retry", async () => {
    listNotesMock.mockRejectedValue(new Error("down"));
    tree();
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });
});
