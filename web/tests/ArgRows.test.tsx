import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ApprovalCard } from "../src/components/approvals/ApprovalCard";
import { makeApprovalCard, makeStep } from "./fixtures";

const getMock = vi.fn();
vi.mock("../src/api/approvals", () => ({
  answerApproval: vi.fn(),
  getApproval: (id: string, full: boolean) => getMock(id, full),
}));
afterEach(() => { cleanup(); getMock.mockReset(); });

const rows = [
  { key: "amount", label: "Amount", value: "9999", truncated: false },
  { key: "income", label: "Kind", value: "Income (money in)", truncated: false },
  { key: "note", label: "Note", value: "<b>coffee</b>", truncated: false },
];

describe("ArgRows", () => {
  it("renders every row as plain text, money first", () => {
    render(<ApprovalCard card={makeApprovalCard({ steps: [makeStep({ tool: "log_expense", rows })] })} />);
    const labels = screen.getAllByRole("term").map((el) => el.textContent);
    expect(labels).toEqual(["Amount", "Kind", "Note"]);
    expect(screen.getByText("9999")).toBeInTheDocument();
    expect(screen.getByText("Income (money in)")).toBeInTheDocument();
    expect(screen.getByText("<b>coffee</b>")).toBeInTheDocument(); // text, not markup
    expect(document.querySelector("dd b")).toBeNull();
  });

  it("Open full shows a long value in full", async () => {
    const cutRows = [{ key: "instructions", label: "Instructions", value: "abc", truncated: true }];
    const wholeRows = [{ key: "instructions", label: "Instructions", value: "abcdefghij", truncated: false }];
    getMock.mockResolvedValue(makeApprovalCard({ steps: [makeStep({ rows: wholeRows })] }));
    render(<ApprovalCard card={makeApprovalCard({ steps: [makeStep({ tool: "create_bot", rows: cutRows })] })} />);
    expect(screen.getByText("abc…")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Open full" }));
    expect(getMock).toHaveBeenCalledWith("card-a", true);
    expect(await screen.findByText("abcdefghij")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Open full" })).not.toBeInTheDocument();
  });
});
