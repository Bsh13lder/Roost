import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ApiError } from "../src/api/client";
import { MemoryNoteRow } from "../src/components/chat/MemoryNoteRow";
import { makeMessage } from "./fixtures";

// A plain function, not a spy: a spy that returns a rejected promise makes vitest report an unhandled rejection.
const forget = vi.hoisted(() => ({ calls: [] as string[], run: (_id: string): Promise<void> => Promise.resolve() }));
vi.mock("../src/api/memories", () => ({ forgetMemory: (id: string) => { forget.calls.push(id); return forget.run(id); } }));

const note = (body: string) => makeMessage({ role: "activity", kind: "memory_note", body });
const NOTE = note(JSON.stringify({ memory_id: "mem-1", kind: "fact", text: "Lives in Madrid" }));
const renderNote = (message = NOTE) => render(<ul><MemoryNoteRow message={message} /></ul>);

beforeEach(() => { forget.calls.length = 0; forget.run = () => Promise.resolve(); });
afterEach(() => cleanup());

describe("MemoryNoteRow", () => {
  it("shows Remembered: and its text with Undo", () => {
    renderNote();
    expect(screen.getByText("Remembered: Lives in Madrid")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Undo: forget Lives in Madrid" })).toHaveTextContent("Undo");
  });

  it("Undo forgets the memory and the line says so", async () => {
    renderNote();
    await userEvent.click(screen.getByRole("button", { name: /Undo/ }));
    expect(forget.calls).toEqual(["mem-1"]);
    expect(await screen.findByText("Forgot: Lives in Madrid")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("an Undo for a memory already gone says Already forgotten", async () => {
    forget.run = () => Promise.reject(new ApiError(404, "Memory not found"));
    renderNote();
    await userEvent.click(screen.getByRole("button", { name: /Undo/ }));
    expect(await screen.findByText("Already forgotten.")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("another failure shows its sentence and keeps Undo", async () => {
    forget.run = () => Promise.reject(new ApiError(500, "Could not forget that."));
    renderNote();
    await userEvent.click(screen.getByRole("button", { name: /Undo/ }));
    expect(await screen.findByText(/Could not forget that\./)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Undo/ })).toBeInTheDocument();
  });

  it("a body that isn't a memory note shows as a plain line with nothing to undo", () => {
    renderNote(note("not json"));
    expect(screen.getByText("not json")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});
