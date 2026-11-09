import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { WorkspaceInternetSwitch } from "../src/components/computer/WorkspaceInternetSwitch";
import { WorkspaceFiles } from "../src/components/computer/WorkspaceFiles";
import { ApiError } from "../src/api/client";
import { makeBot } from "./fixtures";

const setMock = vi.fn();
vi.mock("../src/api/workspace", () => ({
  setWorkspaceInternet: (botId: string, on: boolean) => setMock(botId, on),
  listWorkspaceFiles: vi.fn(),
  wipeWorkspace: vi.fn(),
}));
afterEach(() => { cleanup(); setMock.mockReset(); });

const SWITCH = { name: "Internet in the workspace" };

describe("WorkspaceInternetSwitch", () => {
  it("is off by default and says the workspace has no internet", () => {
    render(<WorkspaceInternetSwitch bot={makeBot()} onChange={() => {}} />);
    expect(screen.getByRole("switch", SWITCH)).toHaveAttribute("aria-checked", "false");
    expect(screen.getByText(/no internet/)).toBeInTheDocument();
  });

  it("turns it on through its route and hands the bot back", async () => {
    const bot = makeBot();
    const onChange = vi.fn();
    setMock.mockResolvedValue({ ...bot, workspace_internet: true });
    render(<WorkspaceInternetSwitch bot={bot} onChange={onChange} />);
    await userEvent.click(screen.getByRole("switch", SWITCH));
    expect(setMock).toHaveBeenCalledWith(bot.id, true);
    await vi.waitFor(() => expect(onChange).toHaveBeenCalledWith({ ...bot, workspace_internet: true }));
  });

  it("says when it is on that keys never go in", () => {
    render(<WorkspaceInternetSwitch bot={{ ...makeBot(), workspace_internet: true }} onChange={() => {}} />);
    expect(screen.getByRole("switch", SWITCH)).toHaveAttribute("aria-checked", "true");
    expect(screen.getByText(/public sites/)).toBeInTheDocument();
  });

  it("shows a refusal in plain words", async () => {
    setMock.mockRejectedValue(new ApiError(503, "Your workspace is unavailable right now."));
    render(<WorkspaceInternetSwitch bot={makeBot()} onChange={() => {}} />);
    await userEvent.click(screen.getByRole("switch", SWITCH));
    expect(await screen.findByText("Your workspace is unavailable right now.")).toBeInTheDocument();
  });

  it("sits inside the Workspace files area", () => {
    render(
      <WorkspaceFiles botId="bot-1" botName="Coder">
        <WorkspaceInternetSwitch bot={makeBot()} onChange={() => {}} />
      </WorkspaceFiles>,
    );
    const area = screen.getByRole("region", { name: "Workspace files" });
    expect(area).toContainElement(screen.getByRole("switch", SWITCH));
  });
});
