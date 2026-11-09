import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { MessageList } from "../src/components/MessageList";
import { answerLines, closedLine, hiddenAnswerIds } from "../src/lib/approvals";
import { makeApprovalCard, makeMessage } from "./fixtures";

const getMock = vi.fn();
vi.mock("../src/api/approvals", () => ({
  answerApproval: vi.fn(),
  getApproval: (...a: unknown[]) => getMock(...a),
}));
afterEach(() => { cleanup(); getMock.mockReset(); });

const choice = { question: "Which day for the plumber?", options: ["Tuesday", "Thursday"], safe: 0, own: true, why: "" };
const card = (over = {}) => makeApprovalCard({ id: "card-c", choice, steps: [], ...over });
const approvalMessage = (id: string, cardId: string, seq: number) =>
  makeMessage({ id, seq, kind: "approval", body: JSON.stringify({ card_id: cardId, kind: "ask", steps: ["Which day for the plumber?"] }) });
const answerMessage = (id: string, body: string, seq: number) => makeMessage({ id, seq, role: "user", kind: "card_answer", body });
const thread = [approvalMessage("m1", "card-c", 1), answerMessage("m2", "Tuesday", 2)];

const list = (approvals: Parameters<typeof MessageList>[0]["approvals"], messages = thread) => (
  <MemoryRouter><MessageList botName="Scout" approvals={approvals} messages={messages} /></MemoryRouter>
);


describe("answerLines and hiddenAnswerIds", () => {
  it("names each card's answer message and hides only those under a card that shows the answer", () => {
    const lines = answerLines([...thread, approvalMessage("m3", "card-y", 3), answerMessage("m4", "fine", 4)]);
    expect(lines.get("card-c")).toEqual({ id: "m2", body: "Tuesday", kind: "ask" });
    const cards = { "card-c": card({ state: "approved" }), "card-y": makeApprovalCard({ id: "card-y", state: "approved" }) };
    // An answered yes/no card says "You said yes: …" itself, so its "Yes: …" bubble is not drawn either.
    expect([...hiddenAnswerIds(lines, cards)].sort()).toEqual(["m2", "m4"]);
  });

  it("keeps a yes/no card's answer line while the card is open or unknown", () => {
    const lines = answerLines([approvalMessage("m3", "card-y", 3), answerMessage("m4", "Yes: Run a program", 4)]);
    expect(hiddenAnswerIds(lines, { "card-y": makeApprovalCard({ id: "card-y" }) }).size).toBe(0);
    expect(hiddenAnswerIds(lines, {}).size).toBe(0);
    expect([...hiddenAnswerIds(lines, { "card-y": makeApprovalCard({ id: "card-y", state: "declined" }) })]).toEqual(["m4"]);
  });

  it("says a closed card's answer in plain words, without the command behind a colon", () => {
    const ran = makeApprovalCard({ state: "approved", steps: [{ ...makeApprovalCard().steps[0], title: "Run a program: curl -sI https://x | head -n 1" }] });
    expect(closedLine(ran)).toBe("You said yes: Run a program");
    expect(closedLine({ ...ran, state: "declined" })).toBe("You said no: Run a program");
  });

  it("keeps the answer line while the card is still open, dismissed or unknown", () => {
    const lines = answerLines(thread);
    expect(hiddenAnswerIds(lines, { "card-c": card() }).size).toBe(0);
    expect(hiddenAnswerIds(lines, { "card-c": card({ state: "declined" }) }).size).toBe(0);
    expect(hiddenAnswerIds(lines, {}).size).toBe(0);
  });
});

describe("your answer bubble under an answered options card", () => {
  it("is not drawn twice: the card's line says it", () => {
    render(list({ "card-c": card({ state: "approved" }) }));
    expect(screen.getByText("Tuesday", { selector: ".choice-done__answer" })).toBeInTheDocument();
    expect(screen.getAllByText("Tuesday")).toHaveLength(1);
  });

  it("stays while the card is open", () => {
    render(list({ "card-c": card() }));
    expect(screen.getAllByText("Tuesday").length).toBeGreaterThan(0);
    expect(screen.queryByText("Tuesday", { selector: ".choice-done__answer" })).toBeNull();
  });

  it("after a reload goes once the closed card is read", async () => {
    getMock.mockResolvedValue(card({ state: "approved" }));
    render(list({}));
    expect(await screen.findByText("Tuesday", { selector: ".choice-done__answer" })).toBeInTheDocument();
    await waitFor(() => expect(screen.getAllByText("Tuesday")).toHaveLength(1));
  });

  it("stays when the closed card cannot be read", async () => {
    getMock.mockRejectedValue(new Error("gone"));
    render(list({}));
    await waitFor(() => expect(getMock).toHaveBeenCalled());
    expect(screen.getByText("Tuesday")).toBeInTheDocument();
  });

  it("a room (no cards passed) keeps every answer line", () => {
    render(list(undefined));
    expect(screen.getByText("Tuesday")).toBeInTheDocument();
  });
});
