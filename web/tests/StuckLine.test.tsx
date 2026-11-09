import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { StatusLabel, statusWords } from "../src/components/StatusLabel";
import { StuckCard } from "../src/components/StuckCard";
import { makeStuckCard, STUCK_LINE } from "./fixtures";

vi.mock("../src/api/computer", () => ({ getControl: vi.fn(), takeControl: vi.fn() }));
vi.mock("../src/api/stuck", () => ({ clearStuck: vi.fn(), giveUpStuck: vi.fn(), openInMainBrowser: vi.fn() }));
afterEach(cleanup);

const LINE = "Stuck on shop.example: a sign-in page. Take control to clear it.";

describe("a Stuck bot says why", () => {
  it("the header shows the Stuck reason", () => {
    render(<StatusLabel status="stuck" activity={LINE} />);
    expect(screen.getByText("Stuck", { selector: ".status-label__text" })).toBeInTheDocument();
    expect(screen.getByText(LINE)).toBeInTheDocument();
  });

  it("a bot waiting on a Sign-in card reads Waiting for you to sign in, in the calm colour, never Stuck", () => {
    const { container } = render(<StatusLabel status="stuck" activity="Waiting for you to sign in to accounts.google.com." />);
    expect(screen.getByText("Waiting for you to sign in", { selector: ".status-label__text" })).toBeInTheDocument();
    expect(screen.getByText("accounts.google.com", { selector: ".status-label__activity" })).toBeInTheDocument();
    expect(screen.queryByText("Stuck")).not.toBeInTheDocument();
    expect(container.firstChild).toHaveClass("status-label--sign_in");
    expect(container.firstChild).not.toHaveClass("status-label--stuck");
  });

  it("statusWords tells a sign-in wait from Stuck", () => {
    expect(statusWords("stuck", "Waiting for you to sign in to x.example.")).toEqual(
      { tone: "sign_in", word: "Waiting for you to sign in", activity: "x.example" });
    expect(statusWords("stuck", LINE)).toEqual({ tone: "stuck", word: "Stuck", activity: LINE });
    expect(statusWords("on_it", "Waiting for you to sign in to x.example.")).toEqual(
      { tone: "on_it", word: "On it", activity: "Waiting for you to sign in to x.example." });
  });

  it("a blocked card still offers Take control", () => {
    const card = makeStuckCard({ state: "blocked", closed_at: "2026-10-14T10:05:00Z" });
    const data = {
      card_id: card.id, bot_id: card.bot_id, reason: card.reason, host: card.host, url: card.url, note: card.note,
      suggest_main_browser: false, line: STUCK_LINE,
    };
    render(<MemoryRouter><StuckCard data={data} card={card} botName="Scout" tainted={false} /></MemoryRouter>);
    expect(screen.getByText("Blocked: shop.example")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Take control" })).toBeInTheDocument();
  });
});
