import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { ReportMessage } from "../src/components/chat/ReportMessage";
import { MessageRow } from "../src/components/MessageRow";
import { makeBot, makeMessage } from "./fixtures";

vi.mock("../src/api/proposals", () => ({ listProposals: vi.fn().mockResolvedValue([]), approveProposal: vi.fn(), declineProposal: vi.fn() }));
vi.mock("../src/hooks/useLiveStore", () => ({ useLiveState: () => ({ routineVersion: { proposals: 0 } }) }));
afterEach(cleanup);

const report = (over: Record<string, unknown> = {}) => makeMessage({
  id: "m-r", kind: "report", author_bot_id: "bot-1",
  body: JSON.stringify({ source: "routine", headline: "Morning digest", text: "Three **new** emails.", routine_id: "r-1",
    run_id: "run-1", log_thread_id: "t-log", tainted: false, routine_name: "Morning digest", ...over }),
});
const inRouter = (node: React.ReactNode) => render(<MemoryRouter><ul>{node}</ul></MemoryRouter>);

describe("ReportMessage (owner, 2026-10-26: a Report is a plain bot message, like Grok)", () => {
  it("draws the text as markdown with no headline and a quiet footer linking the run log", async () => {
    inRouter(<ReportMessage message={report({ headline: "A headline only the server keeps" })} />);
    expect((await screen.findByText("new")).tagName).toBe("STRONG");
    expect(screen.queryByText("A headline only the server keeps")).not.toBeInTheDocument();
    expect(screen.queryByRole("heading")).not.toBeInTheDocument();
    expect(screen.getByText("↻ Morning digest")).toHaveClass("report__foot-name");
    const log = screen.getByRole("link", { name: "Open run log" });
    expect(log).toHaveTextContent("Run log ›");
    expect(log).toHaveAttribute("href", "/bots/bot-1/routines/r-1/log");
  });

  it("an older Report with no routine name still says it came from a routine", () => {
    inRouter(<ReportMessage message={report({ routine_name: undefined })} />);
    expect(screen.getByText("↻ Routine")).toBeInTheDocument();
  });

  it("a missed-reminders summary is a bubble with a Reminder footer and no run-log link", async () => {
    inRouter(<ReportMessage message={report({ routine_id: null, source: "reminder", text: "These passed:\n\n- Pay rent" })} />);
    expect(screen.getByText("🔔 Reminder")).toBeInTheDocument();
    expect(await screen.findByText("Pay rent")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Open run log" })).not.toBeInTheDocument();
  });

  it("shows the headline when a Report has no text", async () => {
    inRouter(<ReportMessage message={report({ text: "" })} />);
    expect(await screen.findByText("Morning digest", { selector: "p" })).toBeInTheDocument();
  });

  it("a tainted report wears the mark", () => {
    inRouter(<ReportMessage message={report({ tainted: true })} />);
    expect(screen.getByRole("button", { name: "From web content" })).toBeInTheDocument();
  });

  it("never turns report text into HTML", () => {
    const { container } = inRouter(<ReportMessage message={report({ text: "<img src=x onerror=alert(1)> <b>hi</b>" })} />);
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("b")).toBeNull();
  });
});

describe("MessageRow routine kinds", () => {
  const row = (message: ReturnType<typeof makeMessage>) =>
    inRouter(<MessageRow message={message} runStart fallbackName="Scout" team={[makeBot()]} />);

  it("quiet lines draw as activity", () => {
    const note = makeMessage({ role: "activity", kind: "routine_note", author_bot_id: "bot-1",
      body: JSON.stringify({ routine_id: "r-1", verb: "created", name: "Digest", text: "Created routine · Digest" }) });
    const { container } = row(note);
    expect(screen.getByText("Created routine · Digest")).toBeInTheDocument();
    expect(container.querySelector("li")).toHaveClass("message--activity");
    cleanup();
    const picked = makeMessage({ role: "activity", kind: "question_note", author_bot_id: "bot-1",
      body: JSON.stringify({ question_id: "q-1", default_choice: "weekly", text: "Picked: weekly · in your question book" }) });
    row(picked);
    expect(screen.getByText("Picked: weekly · in your question book")).toBeInTheDocument();
  });

  it("a report kind draws in the bot's own bubble row, and a broken body falls back to its text", async () => {
    const { container } = row(report());
    expect(await screen.findByText("new")).toBeInTheDocument();
    expect(container.querySelector("li")).toHaveClass("message--bot");
    expect(container.querySelector(".report .message__body")).not.toBeNull();
    cleanup();
    row(makeMessage({ kind: "report", body: "not json", author_bot_id: "bot-1" }));
    expect(screen.getByText("not json")).toBeInTheDocument();
  });
});
