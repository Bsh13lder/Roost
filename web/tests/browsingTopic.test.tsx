import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ApprovalModeCard } from "../src/components/profile/ApprovalModeCard";
import { makeBot } from "./fixtures";

const setApprovalMock = vi.fn();
vi.mock("../src/api/bots", () => ({
  setApproval: (...args: unknown[]) => setApprovalMock(...args),
}));
afterEach(() => { cleanup(); setApprovalMock.mockReset(); });

const approval = (ask_topics: string[] = [], auto_review?: boolean) =>
  ({ mode: "ask", ask_topics, locked_topics: ["posting"], auto_review }) as never;
const linuxBot = (ask_topics: string[] = [], auto_review?: boolean) =>
  makeBot({ computer: "linux", approval: approval(ask_topics, auto_review) });

describe("Browsing actions: the chat mode's three states (owner decision 2026-10-25)", () => {
  it("defaults to Just browse, with its line as the hint", () => {
    render(<ApprovalModeCard bot={linuxBot()} onChange={vi.fn()} />);
    expect(screen.getByRole("group", { name: "Browsing actions" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Just browse" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Ask me" })).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByRole("button", { name: "Full auto" })).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByText("Ordinary clicks just happen. Buttons it can't read still ask.")).toBeInTheDocument();
  });

  it("shows Full auto and Ask me from the bot", () => {
    const { rerender } = render(<ApprovalModeCard bot={linuxBot([], true)} onChange={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Full auto" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText(/A checker looks at buttons it can't read first/)).toBeInTheDocument();
    rerender(<ApprovalModeCard bot={linuxBot(["browsing"])} onChange={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Ask me" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText("Every click on its computer waits for your OK.")).toBeInTheDocument();
  });

  it("each choice is one save with the topics and the checker", async () => {
    const saved = linuxBot(["money", "browsing"]);
    setApprovalMock.mockResolvedValue(saved);
    const onChange = vi.fn();
    const { rerender } = render(<ApprovalModeCard bot={linuxBot(["money"])} onChange={onChange} />);
    await userEvent.click(screen.getByRole("button", { name: "Ask me" }));
    expect(setApprovalMock).toHaveBeenCalledWith("bot-1", "ask", ["money", "browsing"], false);
    expect(onChange).toHaveBeenCalledWith(saved);
    rerender(<ApprovalModeCard bot={saved} onChange={onChange} />);
    await userEvent.click(screen.getByRole("button", { name: "Full auto" }));
    expect(setApprovalMock).toHaveBeenLastCalledWith("bot-1", "ask", ["money"], true);
  });

  it("a failed save says why and keeps the old state", async () => {
    setApprovalMock.mockRejectedValue(new Error("boom"));
    const onChange = vi.fn();
    render(<ApprovalModeCard bot={linuxBot()} onChange={onChange} />);
    await userEvent.click(screen.getByRole("button", { name: "Full auto" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(onChange).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Just browse" })).toHaveAttribute("aria-pressed", "true");
  });

  it("is shown only for a bot on its Linux computer", () => {
    render(<ApprovalModeCard bot={makeBot({ computer: "mac_brave", approval: approval() })} onChange={vi.fn()} />);
    expect(screen.queryByRole("group", { name: "Browsing actions" })).not.toBeInTheDocument();
  });
});
