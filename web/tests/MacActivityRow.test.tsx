import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MacActivityRow } from "../src/components/chat/MacActivityRow";
import { ApiError } from "../src/api/client";
import { makeMessage } from "./fixtures";

const undoMock = vi.fn();
vi.mock("../src/api/mac", () => ({ undoActivity: (id: string) => undoMock(id) }));
afterEach(() => { cleanup(); undoMock.mockReset(); });

const UNDO = { kind: "content", path: "/Users/me/MySpace/grtasks.md", backup_id: "b1", expected_sha256: "abc", grant_id: "g1" };
const line = (over: Record<string, unknown> = {}) => makeMessage({
  id: "act-1", role: "activity", kind: "mac_activity", author_bot_id: "bot-1",
  body: JSON.stringify({ op: "edit", label: "MySpace", path: "/Users/me/MySpace/grtasks.md", plus: 2, minus: 1, tainted_basis: false, undo: UNDO, ...over }),
});
const row = (message = line()) => render(<ul><MacActivityRow message={message} /></ul>);

describe("MacActivityRow", () => {
  it("shows the line and Undo calls the undo route", async () => {
    undoMock.mockResolvedValue({ message: makeMessage({ id: "act-2" }) });
    row();
    expect(screen.getByText("Edited grtasks.md · MySpace (+2 −1)")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Undo" }));
    expect(undoMock).toHaveBeenCalledWith("act-1");
    await vi.waitFor(() => expect(screen.queryByRole("button", { name: "Undo" })).not.toBeInTheDocument());
  });

  it("a 409 shows the plain reason", async () => {
    undoMock.mockRejectedValue(new ApiError(409, "The file changed since; nothing was undone."));
    row();
    await userEvent.click(screen.getByRole("button", { name: "Undo" }));
    expect(await screen.findByText("The file changed since; nothing was undone.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Undo" })).not.toBeInTheDocument();
  });

  it("says each kind of change", () => {
    const cases: Array<[Record<string, unknown>, string]> = [
      [{ op: "create" }, "Created grtasks.md · MySpace"],
      [{ op: "rename", new_path: "/Users/me/MySpace/new.md" }, "Renamed grtasks.md → new.md · MySpace"],
      [{ op: "trash" }, "Moved grtasks.md to the trash · MySpace"],
      [{ op: "undo", undid: "edit", undo: null }, "Undid the edit of grtasks.md · MySpace"],
      [{ op: "undo", undid: "trash", undo: null }, "Moved grtasks.md back from the trash · MySpace"],
      [{ tainted_basis: true }, "Edited grtasks.md · MySpace (+2 −1) · Based on outside content"],
    ];
    for (const [over, text] of cases) {
      row(line(over));
      expect(screen.getByText(text)).toBeInTheDocument();
      cleanup();
    }
  });

  it("a line with nothing to undo has no button", () => {
    row(line({ undo: null }));
    expect(screen.queryByRole("button", { name: "Undo" })).not.toBeInTheDocument();
  });

  it("falls back to a plain line for a body it cannot read", () => {
    row(makeMessage({ role: "activity", kind: "mac_activity", body: "not json" }));
    expect(screen.getByText("Changed a file")).toBeInTheDocument();
  });
});
