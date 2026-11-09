import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ApprovalCard } from "../src/components/approvals/ApprovalCard";
import { closedLine } from "../src/lib/approvals";
import { makeApprovalCard, makeStep } from "./fixtures";

// The Send card (owner, 2026-11-03): every box the bot typed, then Send · Don't send · Change it….
const answerMock = vi.fn();
vi.mock("../src/api/approvals", () => ({
  answerApproval: (id: string, answer: string, text?: string) => answerMock(id, answer, text),
  getApproval: vi.fn(() => new Promise(() => undefined)),   // the button's picture never arrives here
}));
afterEach(() => { cleanup(); answerMock.mockReset(); });

const LETTER = "Hi! I have built REST APIs in Node.js for six years.\nI can start this week.";
const sendStep = makeStep({
  tool: "click", topic: "browsing", title: "Send message", detail: "", floor: "commit_click",
  rows: [
    { key: "site", label: "Site", value: "www.upwork.com", truncated: false },
    { key: "draft", label: "Cover letter", value: LETTER, truncated: false },
    { key: "draft_2", label: "Amount", value: "1500", truncated: false },
    { key: "why", label: "Why you see this", value: "I wrote this text myself.", truncated: false },
  ],
});
const sendCard = (over = {}) => makeApprovalCard({ steps: [sendStep], send: true, tainted: true, from_web: false, ...over });

describe("Send card", () => {
  it("shows every box's text in full and the three buttons, with no web chip when the text is the bot's", () => {
    render(<ApprovalCard card={sendCard()} />);
    expect(screen.getByText("Cover letter")).toBeInTheDocument();
    expect(screen.getByText(/I can start this week/)).toBeInTheDocument();
    expect(screen.getByText("Amount")).toBeInTheDocument();
    for (const name of ["Send", "Don't send", "Change it…"]) {
      expect(screen.getByRole("button", { name })).toBeInTheDocument();
    }
    expect(screen.queryByRole("button", { name: "Yes" })).not.toBeInTheDocument();
    expect(screen.queryByText("from web content")).not.toBeInTheDocument();
  });

  it("keeps the web chip when the text came from a page", () => {
    render(<ApprovalCard card={sendCard({ from_web: true })} />);
    expect(screen.getByText("from web content")).toBeInTheDocument();
  });

  it("Send answers yes", async () => {
    answerMock.mockResolvedValue({ ...sendCard(), state: "approved", closed_at: "x" });
    render(<ApprovalCard card={sendCard()} />);
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(answerMock).toHaveBeenCalledWith("card-a", "yes", undefined);
    expect(await screen.findByText("You said send: Send message")).toBeInTheDocument();
  });

  it("Don't send answers no", async () => {
    answerMock.mockResolvedValue({ ...sendCard(), state: "declined", closed_at: "x" });
    render(<ApprovalCard card={sendCard()} />);
    await userEvent.click(screen.getByRole("button", { name: "Don't send" }));
    expect(answerMock).toHaveBeenCalledWith("card-a", "no", undefined);
    expect(await screen.findByText("Not sent: Send message")).toBeInTheDocument();
  });

  it("Change it opens a box and sends your words as an edit", async () => {
    answerMock.mockResolvedValue({ ...sendCard(), state: "edited", closed_at: "x" });
    render(<ApprovalCard card={sendCard()} />);
    await userEvent.click(screen.getByRole("button", { name: "Change it…" }));
    const box = screen.getByRole("textbox", { name: "What should it say instead?" });
    expect(screen.getByRole("button", { name: "Send change" })).toBeDisabled();
    await userEvent.type(box, "Say I start Monday");
    await userEvent.click(screen.getByRole("button", { name: "Send change" }));
    expect(answerMock).toHaveBeenCalledWith("card-a", "edit", "Say I start Monday");
    expect(await screen.findByText("You asked for a change: Send message")).toBeInTheDocument();
  });

  it("a closed ordinary Ask card keeps its lines", () => {
    const card = makeApprovalCard();
    expect(closedLine({ ...card, state: "approved" })).toBe("You said yes: Edit grtasks.md in MySpace");
    expect(closedLine({ ...card, state: "declined" })).toBe("You said no: Edit grtasks.md in MySpace");
  });

  it("an ordinary Ask card keeps Yes and No", () => {
    render(<ApprovalCard card={makeApprovalCard()} />);
    expect(screen.getByRole("button", { name: "Yes" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Change it…" })).not.toBeInTheDocument();
  });
});
