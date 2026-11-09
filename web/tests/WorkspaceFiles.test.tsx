import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { WorkspaceFiles } from "../src/components/computer/WorkspaceFiles";
import { ApiError } from "../src/api/client";

const listMock = vi.fn();
const wipeMock = vi.fn();
vi.mock("../src/api/workspace", () => ({
  listWorkspaceFiles: (botId: string, path: string) => listMock(botId, path),
  wipeWorkspace: (botId: string) => wipeMock(botId),
}));
afterEach(() => { cleanup(); listMock.mockReset(); wipeMock.mockReset(); });

describe("WorkspaceFiles", () => {
  it("loads nothing until asked, then walks into a folder and back up", async () => {
    listMock.mockResolvedValueOnce({ path: "", entries: [
      { name: "src", kind: "dir", size: null }, { name: "a.py", kind: "file", size: 12 }], more: false });
    listMock.mockResolvedValueOnce({ path: "src", entries: [], more: true });
    listMock.mockResolvedValueOnce({ path: "", entries: [], more: false });
    render(<WorkspaceFiles botId="bot-1" botName="Coder" />);
    expect(listMock).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Show files" }));
    expect(await screen.findByText("a.py · 12 bytes")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "src/" }));
    expect(listMock).toHaveBeenLastCalledWith("bot-1", "src");
    expect(await screen.findByText("/workspace/src")).toBeInTheDocument();
    expect(screen.getByText("No files yet.")).toBeInTheDocument();
    expect(screen.getByText("More files are not shown.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Up" }));
    expect(listMock).toHaveBeenLastCalledWith("bot-1", "");
  });

  it("says why it couldn't list", async () => {
    listMock.mockRejectedValue(new ApiError(503, "Your workspace is unavailable right now."));
    render(<WorkspaceFiles botId="bot-1" botName="Coder" />);
    await userEvent.click(screen.getByRole("button", { name: "Show files" }));
    expect(await screen.findByText("Your workspace is unavailable right now.")).toBeInTheDocument();
  });

  it("wipes only after the confirm, then says so quietly and shows the empty workspace", async () => {
    listMock.mockResolvedValueOnce({ path: "", entries: [{ name: "a.py", kind: "file", size: 12 }], more: false });
    wipeMock.mockResolvedValue({ removed: 3 });
    render(<WorkspaceFiles botId="bot-1" botName="Coder" />);
    await userEvent.click(screen.getByRole("button", { name: "Show files" }));
    expect(await screen.findByText("a.py · 12 bytes")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Wipe workspace" }));
    expect(screen.getByText("Delete every file in Coder's workspace? This can't be undone.")).toBeInTheDocument();
    expect(wipeMock).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByText(/This can't be undone/)).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Wipe workspace" }));
    await userEvent.click(screen.getByRole("button", { name: "Wipe Coder's workspace for good" }));
    expect(wipeMock).toHaveBeenCalledWith("bot-1");
    expect(await screen.findByText("Workspace wiped.")).toBeInTheDocument();
    expect(screen.queryByText("a.py · 12 bytes")).not.toBeInTheDocument();
    expect(screen.getByText("No files yet.")).toBeInTheDocument();
  });

  it("says why a wipe failed", async () => {
    wipeMock.mockRejectedValue(new ApiError(503, "Couldn't wipe the workspace. Some files may be left; try again."));
    render(<WorkspaceFiles botId="bot-1" botName="Coder" />);
    await userEvent.click(screen.getByRole("button", { name: "Wipe workspace" }));
    await userEvent.click(screen.getByRole("button", { name: "Wipe Coder's workspace for good" }));
    expect(await screen.findByText("Couldn't wipe the workspace. Some files may be left; try again.")).toBeInTheDocument();
    expect(screen.queryByText("Workspace wiped.")).not.toBeInTheDocument();
  });
});
