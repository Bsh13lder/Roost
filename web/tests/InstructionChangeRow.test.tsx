import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { InstructionChangeRow } from "../src/components/chat/InstructionChangeRow";
import { MessageRow } from "../src/components/MessageRow";
import { ApiError } from "../src/api/client";
import { parseInstructionChange } from "../src/lib/instructionChange";
import { makeMessage } from "./fixtures";

const undoMock = vi.fn();
vi.mock("../src/api/instructions", () => ({ undoInstructionChange: (id: string) => undoMock(id) }));
afterEach(() => { cleanup(); undoMock.mockReset(); });

const line = (over: Record<string, unknown> = {}) => makeMessage({
  id: "chg-1", role: "activity", kind: "instruction_change", author_bot_id: "bot-1",
  body: JSON.stringify({ section: "Tone", before: "old", after: "new", why: "asked", undone: false, ...over }),
});
const row = (message = line()) => render(<ul><InstructionChangeRow message={message} /></ul>);

describe("InstructionChangeRow", () => {
  it("says which section changed and Undo calls the undo route", async () => {
    undoMock.mockResolvedValue({ message: line({ undone: true }) });
    row();
    expect(screen.getByText("Updated my instructions: Tone")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Undo" }));
    expect(undoMock).toHaveBeenCalledWith("chg-1");
    expect(await screen.findByText("Updated my instructions: Tone · Undone")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Undo" })).not.toBeInTheDocument();
  });

  it("a 409 shows the plain reason and keeps no button", async () => {
    undoMock.mockRejectedValue(new ApiError(409, "Your bot's instructions changed since, so nothing was undone."));
    row();
    await userEvent.click(screen.getByRole("button", { name: "Undo" }));
    expect(await screen.findByText("Your bot's instructions changed since, so nothing was undone.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Undo" })).not.toBeInTheDocument();
  });

  it("an undone line has no button", () => {
    row(line({ undone: true }));
    expect(screen.getByText("Updated my instructions: Tone · Undone")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Undo" })).not.toBeInTheDocument();
  });

  it("reads a body it cannot use as a plain line", () => {
    expect(parseInstructionChange("not json")).toBeNull();
    expect(parseInstructionChange(JSON.stringify({ section: 3 }))).toBeNull();
    row(makeMessage({ role: "activity", kind: "instruction_change", body: "not json" }));
    expect(screen.getByText("Updated my instructions")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Undo" })).not.toBeInTheDocument();
  });

  it("MessageRow draws the line for an instruction_change message", () => {
    render(<ul><MessageRow message={line()} runStart={false} team={[]} fallbackName="Scout" /></ul>);
    expect(screen.getByText("Updated my instructions: Tone")).toBeInTheDocument();
  });
});
