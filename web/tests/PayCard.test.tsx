import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ApprovalCard } from "../src/components/approvals/ApprovalCard";
import { makeApprovalCard, makeStep } from "./fixtures";

// The Pay card (owner, 2026-11-05): fields only for the card parts the page asks for; a saved card asks only the
// security code; Pay sends the card in the body, Don't pay answers no.
const answerMock = vi.fn();
const fieldsMock = vi.fn();
const payMock = vi.fn();
vi.mock("../src/api/approvals", () => ({
  answerApproval: (id: string, answer: string, text?: string) => answerMock(id, answer, text),
  getApproval: vi.fn(() => new Promise(() => undefined)),
}));
vi.mock("../src/api/payments", () => ({
  getPayFields: (id: string) => fieldsMock(id),
  payCard: (id: string, body: unknown) => payMock(id, body),
}));
afterEach(() => { cleanup(); answerMock.mockReset(); fieldsMock.mockReset(); payMock.mockReset(); });

const payStep = makeStep({ tool: "click", topic: "browsing", title: "Click 'Pay 36 EUR'", detail: "",
  floor: "commit_click", rows: [{ key: "site", label: "Site", value: "shop.test", truncated: false }] });
const payCardOut = (over = {}) => makeApprovalCard({ steps: [payStep], pay: true, tainted: true, ...over });
const ALL = { parts: ["number", "exp", "name", "cvc"], refusal: "", cards: [] };

describe("Pay card", () => {
  it("shows the card fields the page asks for with card autocomplete, and Pay sends them", async () => {
    fieldsMock.mockResolvedValue(ALL);
    payMock.mockResolvedValue({ ...payCardOut(), state: "approved", closed_at: "x" });
    render(<ApprovalCard card={payCardOut()} />);
    const number = await screen.findByLabelText("Card number");
    expect(number).toHaveAttribute("autocomplete", "cc-number");
    expect(screen.getByLabelText("Security code (CVC)")).toHaveAttribute("type", "password");
    await userEvent.type(number, "4242424242424242");
    await userEvent.type(screen.getByLabelText("Expiry (MM/YY)"), "12/28");
    await userEvent.type(screen.getByLabelText("Name on card"), "Ana Garcia");
    await userEvent.type(screen.getByLabelText("Security code (CVC)"), "737");
    await userEvent.click(screen.getByRole("checkbox"));
    await userEvent.click(screen.getByRole("button", { name: "Pay" }));
    expect(payMock).toHaveBeenCalledWith("card-a", {
      number: "4242424242424242", exp: "12/28", name: "Ana Garcia", cvc: "737", save: true });
    expect(await screen.findByText("You paid: Click 'Pay 36 EUR'")).toBeInTheDocument();
  });

  it("a saved card asks only the security code", async () => {
    fieldsMock.mockResolvedValue({ ...ALL, cards: [{ id: "c1", brand: "visa", last4: "4242", last_used_at: null }] });
    payMock.mockResolvedValue({ ...payCardOut(), state: "approved", closed_at: "x" });
    render(<ApprovalCard card={payCardOut()} />);
    await userEvent.click(await screen.findByRole("radio", { name: "Visa ending 4242" }));
    expect(screen.queryByLabelText("Card number")).not.toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Security code (CVC)"), "737");
    await userEvent.click(screen.getByRole("button", { name: "Pay" }));
    expect(payMock).toHaveBeenCalledWith("card-a", { card_id: "c1", cvc: "737" });
  });

  it("a protected card box says to take control, and Pay still answers", async () => {
    fieldsMock.mockResolvedValue({ parts: [], refusal: "This site's card box is protected.", cards: [] });
    render(<ApprovalCard card={payCardOut()} />);
    expect(await screen.findByText("This site's card box is protected.")).toBeInTheDocument();
    expect(screen.queryByLabelText("Card number")).not.toBeInTheDocument();
  });

  it("a refused card clears the security code so it is typed again", async () => {
    fieldsMock.mockResolvedValue({ ...ALL, parts: ["cvc"] });
    payMock.mockRejectedValue(new Error("The security code doesn't look right."));
    render(<ApprovalCard card={payCardOut()} />);
    const cvc = await screen.findByLabelText("Security code (CVC)");
    await userEvent.type(cvc, "12");
    await userEvent.click(screen.getByRole("button", { name: "Pay" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(cvc).toHaveValue("");
  });

  it("Don't pay answers no", async () => {
    fieldsMock.mockResolvedValue(ALL);
    answerMock.mockResolvedValue({ ...payCardOut(), state: "declined", closed_at: "x" });
    render(<ApprovalCard card={payCardOut()} />);
    await userEvent.click(await screen.findByRole("button", { name: "Don't pay" }));
    expect(answerMock).toHaveBeenCalledWith("card-a", "no", undefined);
    expect(await screen.findByText("Not paid: Click 'Pay 36 EUR'")).toBeInTheDocument();
  });
});
