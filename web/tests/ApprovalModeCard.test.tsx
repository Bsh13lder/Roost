import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ApprovalModeCard } from "../src/components/profile/ApprovalModeCard";
import { makeBot } from "./fixtures";

const setApprovalMock = vi.fn();
vi.mock("../src/api/bots", () => ({
  setApproval: (id: string, mode: string, topics: string[]) => setApprovalMock(id, mode, topics),
}));
afterEach(() => { cleanup(); setApprovalMock.mockReset(); });

const approval = (mode: "ask" | "auto_edit" | "plan", ask_topics: string[] = []) =>
  ({ mode, ask_topics, locked_topics: ["posting"] }) as never;

describe("ApprovalModeCard", () => {
  it("shows the bot's mode and saves a new one", async () => {
    const saved = makeBot({ approval: approval("plan") });
    setApprovalMock.mockResolvedValue(saved);
    const onChange = vi.fn();
    render(<ApprovalModeCard bot={makeBot({ approval: approval("ask") })} onChange={onChange} />);
    expect(screen.getByRole("button", { name: "Ask every time" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText("Every change waits for your OK on a card.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Review first" }));
    expect(setApprovalMock).toHaveBeenCalledWith("bot-1", "plan", []);
    expect(onChange).toHaveBeenCalledWith(saved);
  });

  it("a topic switch saves the topic list", async () => {
    setApprovalMock.mockResolvedValue(makeBot());
    render(<ApprovalModeCard bot={makeBot({ approval: approval("auto_edit", ["money"]) })} onChange={vi.fn()} />);
    expect(screen.getByRole("switch", { name: "Money" })).toHaveAttribute("aria-checked", "true");
    await userEvent.click(screen.getByRole("switch", { name: "Files" }));
    expect(setApprovalMock).toHaveBeenCalledWith("bot-1", "auto_edit", ["money", "files"]);
    await userEvent.click(screen.getByRole("switch", { name: "Money" }));
    expect(setApprovalMock).toHaveBeenLastCalledWith("bot-1", "auto_edit", []);
  });

  it("posting is locked on", async () => {
    render(<ApprovalModeCard bot={makeBot({ approval: approval("auto_edit") })} onChange={vi.fn()} />);
    const posting = screen.getByRole("switch", { name: /Posting and sending/ });
    expect(posting).toBeDisabled();
    expect(posting).toHaveAttribute("aria-checked", "true");
    expect(screen.getByText(/always asks/)).toBeInTheDocument();
  });

  it("a failed save shows the error and keeps the old mode", async () => {
    const { ApiError } = await import("../src/api/client");
    setApprovalMock.mockRejectedValue(new ApiError(500, "The server is busy."));
    const onChange = vi.fn();
    render(<ApprovalModeCard bot={makeBot({ approval: approval("ask") })} onChange={onChange} />);
    await userEvent.click(screen.getByRole("button", { name: "Auto-edit" }));
    expect(await screen.findByText("The server is busy.")).toBeInTheDocument();
    expect(onChange).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Ask every time" })).toHaveAttribute("aria-pressed", "true");
  });

  it("has a Programs switch, off by default, that saves the programs topic", async () => {
    setApprovalMock.mockResolvedValue(makeBot());
    render(<ApprovalModeCard bot={makeBot({ approval: approval("auto_edit") })} onChange={vi.fn()} />);
    const programs = screen.getByRole("switch", { name: "Programs" });
    expect(programs).toHaveAttribute("aria-checked", "false");
    await userEvent.click(programs);
    expect(setApprovalMock).toHaveBeenCalledWith("bot-1", "auto_edit", ["programs"]);
  });
});
