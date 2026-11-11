import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { MessageRow, type MessageRowProps } from "../src/components/MessageRow";
import { makeApprovalCard, makeBot, makeMessage } from "./fixtures";

vi.mock("../src/api/approvals", () => ({ answerApproval: vi.fn(), getApproval: vi.fn() }));
vi.mock("../src/api/mac", () => ({ undoActivity: vi.fn() }));

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

const SCOUT = makeBot({ id: "bot-1", name: "Scout" });

function renderRow(overrides: Partial<MessageRowProps> = {}) {
  const props: MessageRowProps = {
    message: makeMessage({ author_bot_id: "bot-1" }), runStart: true, fallbackName: "Scout", team: [SCOUT], ...overrides,
  };
  return render(<MemoryRouter><ul><MessageRow {...props} /></ul></MemoryRouter>);
}

describe("MessageRow (redesign P2)", () => {
  it("draws a computer_restart line as plain words (self-healing, 2026-11-10)", () => {
    const body = "My computer stopped answering, so I restarted it.";
    const { container } = renderRow({ message: makeMessage({ role: "system", kind: "computer_restart", body }) });
    expect(container.querySelector("li")).toHaveClass("message--notice", "message--notice-computer_restart");
    expect(screen.getByText(body)).toBeInTheDocument();
  });

  it("draws a memory_note as the Remembered line", () => {
    const body = JSON.stringify({ memory_id: "mem-1", kind: "fact", text: "Lives in Madrid" });
    const { container } = renderRow({ message: makeMessage({ role: "activity", kind: "memory_note", author_bot_id: "bot-1", body }) });
    expect(container.querySelector("li")).toHaveClass("message--memory");
    expect(screen.getByText("Remembered: Lives in Madrid")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Undo: forget Lives in Madrid" })).toBeInTheDocument();
  });

  it("draws a memory_offer as the Not remembered line with Remember it", () => {
    const body = JSON.stringify({ text: "Task alerts only", kind: "preference", importance: 5, memory_id: null });
    const { container } = renderRow({ message: makeMessage({ role: "activity", kind: "memory_offer", tainted: true, author_bot_id: "bot-1", body }) });
    expect(container.querySelector("li")).toHaveClass("message--memory-offer");
    expect(screen.getByText(/^Not remembered: Task alerts only\./)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Remember it: Task alerts only" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "From web content" })).toBeInTheDocument();
  });

  it("draws a bot's reply as markdown once the renderer has loaded", async () => {
    renderRow({ message: makeMessage({ author_bot_id: "bot-1", body: "**Done.** See [[Garden plan]]." }) });
    expect((await screen.findByText("Done.")).tagName).toBe("STRONG");
    expect(screen.getByText("Garden plan")).toHaveClass("wikilink-chip");
  });

  it("keeps your own message as you typed it, in an accent bubble", () => {
    const { container } = renderRow({ message: makeMessage({ role: "user", body: "**not bold** please" }) });
    expect(screen.getByText("**not bold** please")).toBeInTheDocument();
    expect(container.querySelector("li")).toHaveClass("message--user");
    expect(container.querySelector("strong")).toBeNull();
  });

  it("makes a long reply a full-width card and keeps a short one a bubble", () => {
    const long = renderRow({ message: makeMessage({ author_bot_id: "bot-1", body: "## Plan\n\n- one\n- two" }) });
    expect(long.container.querySelector("li")).toHaveClass("message--card");
    cleanup();
    const short = renderRow({ message: makeMessage({ author_bot_id: "bot-1", body: "On it." }) });
    expect(short.container.querySelector("li")).not.toHaveClass("message--card");
  });

  it("shows the Madrid time it was sent and copies the message as written", async () => {
    const user = userEvent.setup();
    renderRow({ message: makeMessage({ author_bot_id: "bot-1", body: "**Done.**", created_at: "2026-10-14T12:19:00Z" }) });
    expect(screen.getByText("14:19")).toHaveAttribute("datetime", "2026-10-14T12:19:00Z");
    await user.click(screen.getByRole("button", { name: "Copy message" }));
    expect(await navigator.clipboard.readText()).toBe("**Done.**");
    expect(screen.getByRole("button", { name: "Copied" })).toBeInTheDocument();
  });

  it("marks a reply written after reading web content", () => {
    renderRow({ message: makeMessage({ author_bot_id: "bot-1", body: "The page says the shop opens at 9.", tainted: true }) });
    expect(screen.getByRole("button", { name: "From web content" })).toBeInTheDocument();
  });

  it("offers no copy and no time on a reply still being written, nor on a card", () => {
    renderRow({ message: makeMessage({ author_bot_id: "bot-1", body: "", seq: 0 }), liveText: "Wri" });
    expect(screen.queryByRole("button", { name: "Copy message" })).toBeNull();
    cleanup();
    const body = JSON.stringify({ name: "Ledger", job: "Keeps the books", avatar: { shape: "wide", color: "#3b82f6", badge: "finance" } });
    renderRow({ message: makeMessage({ kind: "suggestion", author_bot_id: "bot-1", body }) });
    expect(screen.getByRole("button", { name: "Create this bot" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Copy message" })).toBeNull();
  });

  it("draws an approval message as its card from the live store, and a closed one as its line", () => {
    const body = JSON.stringify({ card_id: "card-a", kind: "ask", steps: ["Edit grtasks.md in MySpace"] });
    const message = makeMessage({ kind: "approval", author_bot_id: "bot-1", body });
    renderRow({ message, approvals: { "card-a": makeApprovalCard() } });
    expect(screen.getByRole("button", { name: "Yes" })).toBeInTheDocument();
    cleanup();
    renderRow({ message, approvals: { "card-a": makeApprovalCard({ state: "approved" }) } });
    expect(screen.getByText("You said yes: Edit grtasks.md in MySpace")).toBeInTheDocument();
    cleanup();
    renderRow({ message });
    expect(screen.getByText("Edit grtasks.md in MySpace")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Yes" })).not.toBeInTheDocument();
  });

  it("draws a proposal card for a plan", () => {
    const body = JSON.stringify({ card_id: "p1", kind: "plan", steps: ["One", "Two"] });
    renderRow({
      message: makeMessage({ kind: "approval", author_bot_id: "bot-1", body }),
      approvals: { p1: makeApprovalCard({ id: "p1", kind: "plan" }) },
    });
    expect(screen.getByRole("button", { name: "Accept" })).toBeInTheDocument();
  });

  it("draws nothing for the never-published approval_result message", () => {
    const { container } = renderRow({ message: makeMessage({ role: "system", kind: "approval_result", body: "Yes: it ran." }) });
    expect(container.querySelector("li")).toBeNull();
    expect(screen.queryByText("Yes: it ran.")).not.toBeInTheDocument();
  });

  it("draws a mac_activity message as the activity line", () => {
    const body = JSON.stringify({ op: "trash", label: "MySpace", path: "/a/b.md", plus: 0, minus: 0, tainted_basis: false, undo: null });
    renderRow({ message: makeMessage({ role: "activity", kind: "mac_activity", body }) });
    expect(screen.getByText("Moved b.md to the trash · MySpace")).toBeInTheDocument();
  });

  it("draws an english_fix line as its quiet card where it stands", () => {
    const body = JSON.stringify({ message_id: "u-9", said: "I goed", corrected: "I went", fixes: [{ wrong: "goed", right: "went" }] });
    const { container } = renderRow({ message: makeMessage({ role: "activity", kind: "english_fix", body }) });
    expect(container.querySelector("li")).toHaveClass("message--english-fix");
    expect(screen.getByText("goed").tagName).toBe("DEL");
    expect(screen.getByText("You said: I goed")).toBeInTheDocument();
  });
});
