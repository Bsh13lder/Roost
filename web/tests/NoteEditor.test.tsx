import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NoteEditor } from "../src/components/notes/NoteEditor";
import { ApiError } from "../src/api/client";
import { RevisionConflictError } from "../src/api/conflict";
import type { NoteOut } from "../src/api/types";

const getNoteMock = vi.fn();
const saveNoteMock = vi.fn();
vi.mock("../src/api/notes", () => ({
  getNote: (...a: unknown[]) => getNoteMock(...a),
  saveNote: (...a: unknown[]) => saveNoteMock(...a),
}));

function note(overrides: Partial<NoteOut> = {}): NoteOut {
  return {
    id: "n1", title: "Ana", tags: ["people"], snippet: "", pinned: false, revision: 1, created_at: "x", updated_at: "x",
    created_by_bot: null, tainted: false, content: "Likes **orchids**. See [[Garden]] and [[Lisbon]].",
    links: [{ target: "garden", title: "Garden", note_id: "n2" }, { target: "lisbon", title: "Lisbon", note_id: null }],
    ...overrides,
  };
}

const onClose = vi.fn();
const onOpenNote = vi.fn();
const onCreateNote = vi.fn();

function renderEditor() {
  return render(<NoteEditor noteId="n1" onClose={onClose} onOpenNote={onOpenNote} onCreateNote={onCreateNote} />);
}

async function replaceText(text: string) {
  const user = userEvent.setup();
  const body = await screen.findByLabelText("Note text");
  await user.clear(body);
  await user.type(body, text);
  await user.tab();
  return user;
}

beforeEach(() => {
  for (const mock of [getNoteMock, saveNoteMock, onClose, onOpenNote, onCreateNote]) mock.mockReset();
  getNoteMock.mockResolvedValue(note());
});
afterEach(() => cleanup());

describe("NoteEditor", () => {
  it("saves an edit against the revision it opened when you leave the field", async () => {
    saveNoteMock.mockResolvedValue(note({ content: "Likes orchids and roses.", revision: 2 }));
    renderEditor();
    await replaceText("Likes orchids and roses.");
    await waitFor(() => expect(saveNoteMock).toHaveBeenCalledWith("n1", {
      base_revision: 1, title: "Ana", content: "Likes orchids and roses.",
    }));
    expect(await screen.findByText("Saved")).toBeInTheDocument();
    expect(saveNoteMock).toHaveBeenCalledTimes(1);
  });

  it("on a stale revision, Keep mine saves over the latest revision", async () => {
    saveNoteMock.mockRejectedValueOnce(new RevisionConflictError(note({ content: "Their text", revision: 3 })))
      .mockResolvedValue(note({ content: "Mine", revision: 4 }));
    renderEditor();
    const user = await replaceText("Mine");
    expect(await screen.findByText(/This note changed somewhere else/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Keep mine" }));
    await waitFor(() => expect(saveNoteMock).toHaveBeenLastCalledWith("n1", {
      base_revision: 3, title: "Ana", content: "Mine",
    }), { timeout: 2000 });
  });

  it("on a stale revision, Load the latest shows their copy and saves nothing more", async () => {
    saveNoteMock.mockRejectedValueOnce(new RevisionConflictError(note({ content: "Their text", revision: 3 })));
    renderEditor();
    const user = await replaceText("Mine");
    await user.click(await screen.findByRole("button", { name: "Load the latest" }));
    expect(screen.getByLabelText("Note text")).toHaveValue("Their text");
    expect(saveNoteMock).toHaveBeenCalledTimes(1);
  });

  it("previews markdown and opens a [[link]] to an existing note", async () => {
    const user = userEvent.setup();
    renderEditor();
    await user.click(await screen.findByRole("button", { name: "Preview" }));
    expect(screen.getByText("orchids").tagName).toBe("STRONG");
    await user.click(screen.getByRole("button", { name: "Garden" }));
    await waitFor(() => expect(onOpenNote).toHaveBeenCalledWith("n2"));
  });

  it("never draws a remote image, shows a link as its real host and survives a broken [[link]]", async () => {
    getNoteMock.mockResolvedValue(note({
      content: "![x](https://evil.example/p?d=1)\n\n[My bank](https://phish.example/login)\n\n[odd](#wikilink/%E0%A4)",
      links: [],
    }));
    const user = userEvent.setup();
    const { container } = renderEditor();
    await user.click(await screen.findByRole("button", { name: "Preview" }));
    expect(container.querySelector("img")).toBeNull();
    expect(screen.getByText("[image: x]")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "phish.example" })).toHaveAttribute("href", "https://phish.example/login");
    expect(screen.queryByText("My bank")).toBeNull();
    expect(screen.getByText("odd").tagName).toBe("SPAN");
  });

  it("offers to create a note for a [[link]] that has none yet", async () => {
    const user = userEvent.setup();
    renderEditor();
    await user.click(await screen.findByRole("button", { name: "Create note Lisbon" }));
    await waitFor(() => expect(onCreateNote).toHaveBeenCalledWith("Lisbon"));
  });

  it("saves what you typed before closing", async () => {
    saveNoteMock.mockResolvedValue(note({ content: `${note().content}!`, revision: 2 }));
    const user = userEvent.setup();
    renderEditor();
    await user.type(await screen.findByLabelText("Note text"), "!");
    await user.click(screen.getByRole("button", { name: "← Notes" }));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(saveNoteMock).toHaveBeenCalledTimes(1);
  });

  // Findings round 1: leaving must never silently throw away the user's text.

  it("keeps the editor open when the save fails, instead of losing the text", async () => {
    saveNoteMock.mockRejectedValue(new ApiError(503, "Service unavailable"));
    const user = userEvent.setup();
    renderEditor();
    await user.type(await screen.findByLabelText("Note text"), "!");
    await user.click(screen.getByRole("button", { name: "← Notes" }));
    expect(await screen.findByText("Not saved: Service unavailable")).toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();
  });

  it("keeps the editor open on a pending conflict, instead of dropping the user's version", async () => {
    saveNoteMock.mockRejectedValueOnce(new RevisionConflictError(note({ content: "Their text", revision: 3 })));
    renderEditor();
    await replaceText("Mine");
    expect(await screen.findByText(/This note changed somewhere else/)).toBeInTheDocument();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "← Notes" }));
    expect(onClose).not.toHaveBeenCalled();
    expect(screen.getByText(/This note changed somewhere else/)).toBeInTheDocument();
    expect(saveNoteMock).toHaveBeenCalledTimes(1);
  });
});
