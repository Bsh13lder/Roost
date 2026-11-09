import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { StuckCard } from "../src/components/StuckCard";
import { ApiError } from "../src/api/client";
import type { StuckCardOut, StuckMessageData } from "../src/api/types";
import { makeStuckCard, STUCK_LINE } from "./fixtures";

const computer = { getControl: vi.fn(), takeControl: vi.fn() };
const stuck = { clearStuck: vi.fn(), giveUpStuck: vi.fn(), openInMainBrowser: vi.fn() };
vi.mock("../src/api/computer", () => ({
  getControl: (id: string) => computer.getControl(id),
  takeControl: (id: string) => computer.takeControl(id),
}));
vi.mock("../src/api/stuck", () => ({
  clearStuck: (id: string) => stuck.clearStuck(id),
  giveUpStuck: (id: string) => stuck.giveUpStuck(id),
  openInMainBrowser: (id: string) => stuck.openInMainBrowser(id),
}));

const CARD = makeStuckCard();
const CLOSED_AT = "2026-10-14T10:05:00Z";
const dataOf = (card: StuckCardOut, line = STUCK_LINE): StuckMessageData => ({
  card_id: card.id, bot_id: card.bot_id, reason: card.reason, host: card.host, url: card.url, note: card.note,
  suggest_main_browser: card.suggest_main_browser, line,
});
const cardView = (card: StuckCardOut | undefined, data = dataOf(CARD), tainted = false) => (
  <MemoryRouter><StuckCard data={data} card={card} botName="Scout" tainted={tainted} /></MemoryRouter>
);
const renderCard = (card: StuckCardOut | undefined, data = dataOf(CARD), tainted = false) =>
  render(cardView(card, data, tainted));
const click = (name: string) => userEvent.click(screen.getByRole("button", { name }));

beforeEach(() => {
  stuck.clearStuck.mockResolvedValue({ ...CARD, state: "cleared", closed_at: CLOSED_AT });
  stuck.giveUpStuck.mockResolvedValue({ ...CARD, state: "given_up", closed_at: CLOSED_AT });
  stuck.openInMainBrowser.mockResolvedValue({ ...CARD, main_opened: true });
  computer.takeControl.mockResolvedValue({ held: true, since: "2026-10-14T10:01:00Z" });
  computer.getControl.mockResolvedValue({ held: false, since: null });
});
afterEach(() => { cleanup(); [...Object.values(computer), ...Object.values(stuck)].forEach((m) => m.mockReset()); });

describe("StuckCard", () => {
  it("an open card shows the bot's line, the address and its four buttons", () => {
    renderCard(CARD);
    const card = screen.getByRole("group", { name: "Stuck on shop.example" });
    expect(card).toHaveTextContent(STUCK_LINE);
    expect(card).toHaveTextContent("https://shop.example/login");
    for (const name of ["Take control", "Try again", "Use my main Brave", "Give up"]) {
      expect(screen.getByRole("button", { name })).toBeEnabled();
    }
    expect(screen.queryByRole("note")).not.toBeInTheDocument();
  });

  it("a card with no address is titled Needs your help and has no main Brave button", () => {
    const asked = makeStuckCard({ reason: "asked", host: "", url: "", note: "Approve the payment" });
    renderCard(asked, dataOf(asked, "I need your help: Approve the payment. Take control to clear it, then give it back."));
    expect(screen.getByRole("group", { name: "Needs your help" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Use my main Brave" })).not.toBeInTheDocument();
  });

  it("Take control holds the computer and says how to give it back", async () => {
    renderCard(CARD);
    await click("Take control");
    expect(computer.takeControl).toHaveBeenCalledWith("bot-1");
    expect(await screen.findByText("You have control. Clear it in Scout's window, then give it back.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "See its screen" })).toHaveAttribute("href", "/bots/bot-1?panel=computer");
    expect(screen.queryByRole("button", { name: "Take control" })).not.toBeInTheDocument();
  });

  it("a card whose computer you already hold opens on the Holding view, so its Give it back survives a visit to the screen", async () => {
    computer.getControl.mockResolvedValue({ held: true, since: "2026-10-14T10:01:00Z" });
    renderCard(CARD);
    expect(await screen.findByText("You have control. Clear it in Scout's window, then give it back.")).toBeInTheDocument();
    expect(computer.getControl).toHaveBeenCalledWith("bot-1");
    expect(computer.takeControl).not.toHaveBeenCalled();
    await click("Give it back");
    expect(stuck.clearStuck).toHaveBeenCalledWith("card-1");
    expect(await screen.findByText("Cleared: shop.example")).toBeInTheDocument();
  });

  it("an answer that you don't hold the computer never undoes a Take control pressed meanwhile", async () => {
    let answer: (value: { held: boolean; since: null }) => void = () => {};
    computer.getControl.mockReturnValue(new Promise((resolve) => { answer = resolve; }));
    renderCard(CARD);
    await click("Take control");
    await screen.findByText("You have control. Clear it in Scout's window, then give it back.");
    await act(async () => answer({ held: false, since: null }));
    expect(screen.getByRole("button", { name: "Give it back" })).toBeInTheDocument();
  });

  it("a failed check of who holds the computer says why and keeps the card's buttons", async () => {
    computer.getControl.mockRejectedValue(new ApiError(503, "desk unavailable"));
    renderCard(CARD);
    expect(await screen.findByRole("alert")).toHaveTextContent("desk unavailable");
    expect(screen.getByRole("button", { name: "Take control" })).toBeEnabled();
  });

  it("a closed or unknown card never asks who holds the computer", () => {
    renderCard({ ...CARD, state: "cleared", closed_at: CLOSED_AT });
    cleanup();
    renderCard(undefined);
    expect(computer.getControl).not.toHaveBeenCalled();
  });

  it("Give it back clears the card, then it folds to Cleared", async () => {
    renderCard(CARD);
    await click("Take control");
    await screen.findByText("You have control. Clear it in Scout's window, then give it back.");
    await click("Give it back");
    expect(stuck.clearStuck).toHaveBeenCalledWith("card-1");
    expect(await screen.findByText("Cleared: shop.example")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("Try again clears the card without taking control", async () => {
    renderCard(CARD);
    await click("Try again");
    expect(stuck.clearStuck).toHaveBeenCalledWith("card-1");
    expect(computer.takeControl).not.toHaveBeenCalled();
    expect(await screen.findByText("Cleared: shop.example")).toBeInTheDocument();
  });

  it("Use my main Brave opens it there, then Done, carry on clears the card", async () => {
    renderCard(CARD);
    await click("Use my main Brave");
    expect(stuck.openInMainBrowser).toHaveBeenCalledWith("card-1");
    expect(await screen.findByText("Opened in your main Brave.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Give up" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Take control" })).not.toBeInTheDocument();
    await click("Done, carry on");
    expect(stuck.clearStuck).toHaveBeenCalledWith("card-1");
    expect(await screen.findByText("Cleared: shop.example")).toBeInTheDocument();
  });

  it("a card already opened in the main Brave offers Done, carry on and Give up", () => {
    renderCard({ ...CARD, main_opened: true });
    expect(screen.getByText("Opened in your main Brave.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Done, carry on" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Give up" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Try again" })).not.toBeInTheDocument();
  });

  it("Reply puts the card's quote in the composer, so your next message answers it", async () => {
    const onReply = vi.fn();
    render(<MemoryRouter><StuckCard data={dataOf(CARD)} card={CARD} botName="Scout" tainted={false} onReply={onReply} /></MemoryRouter>);
    const reply = screen.getByRole("button", { name: "Reply" });
    expect(reply).toHaveClass("btn--ghost");
    await userEvent.click(reply);
    expect(onReply).toHaveBeenCalledTimes(1);
    expect(stuck.clearStuck).not.toHaveBeenCalled();
  });

  it("with nowhere to reply (a read-only chat) the card has no Reply", () => {
    renderCard(CARD);
    expect(screen.queryByRole("button", { name: "Reply" })).not.toBeInTheDocument();
  });

  it("a card you answered in the chat folds to You answered in the chat", () => {
    renderCard({ ...CARD, state: "replied", closed_at: CLOSED_AT });
    expect(screen.getByText("You answered in the chat")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reply" })).not.toBeInTheDocument();
  });

  it("Give up stops the task, then it folds to Stopped", async () => {
    renderCard(CARD);
    await click("Give up");
    expect(stuck.giveUpStuck).toHaveBeenCalledWith("card-1");
    expect(await screen.findByText("Stopped: shop.example")).toBeInTheDocument();
  });

  it("the bot's suggestion makes Use my main Brave the highlighted button", () => {
    const suggested = makeStuckCard({ suggest_main_browser: true });
    renderCard(suggested, dataOf(suggested));
    expect(screen.getByRole("button", { name: "Use my main Brave" })).toHaveClass("btn--primary");
    expect(screen.getByRole("button", { name: "Take control" })).not.toHaveClass("btn--primary");
  });

  it("a suggestion for the main Brave with no address highlights Take control, not a button that isn't there", () => {
    const asked = makeStuckCard({ reason: "asked", host: "", url: "", note: "Approve the payment", suggest_main_browser: true });
    renderCard(asked, dataOf(asked));
    expect(screen.queryByRole("button", { name: "Use my main Brave" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Take control" })).toHaveClass("btn--primary");
  });

  it("a card from a run that read the web warns before you open its link", () => {
    renderCard(CARD, dataOf(CARD), true);
    expect(screen.getByRole("note")).toHaveTextContent(
      "This link came from a web page the bot read. Check it before you open it.",
    );
  });

  it("a failed button says why and leaves the card open", async () => {
    stuck.clearStuck.mockRejectedValue(new ApiError(409, "This card is already closed."));
    renderCard(CARD);
    await click("Try again");
    expect(await screen.findByRole("alert")).toHaveTextContent("This card is already closed.");
    expect(screen.getByRole("button", { name: "Try again" })).toBeEnabled();
  });

  it.each([
    ["cleared", "Cleared: shop.example"],
    ["given_up", "Stopped: shop.example"],
    ["blocked", "Blocked: shop.example"],
  ] as const)("a %s card folds to one line", (state, line) => {
    renderCard({ ...CARD, state, closed_at: CLOSED_AT });
    expect(screen.getByRole("group", { name: line })).toHaveTextContent(line);
    // Only a blocked card keeps a button: Take control (StuckLine.test.tsx).
    expect(screen.queryAllByRole("button")).toHaveLength(state === "blocked" ? 1 : 0);
  });

  it.each([
    ["cleared", "Cleared"],
    ["given_up", "Stopped"],
    ["blocked", "Blocked"],
  ] as const)("a %s card with no site folds to the bare word, with or without a note", (state, word) => {
    const asked = makeStuckCard({ reason: "asked", host: "", url: "", note: "Approve the payment", state, closed_at: CLOSED_AT });
    renderCard(asked, dataOf(asked));
    expect(screen.getByRole("group", { name: word })).toBeInTheDocument();   // the name is matched whole
    expect(screen.getByText(word)).toBeInTheDocument();
    cleanup();
    const bare = makeStuckCard({ reason: "asked", host: "", url: "", note: "", state, closed_at: CLOSED_AT });
    renderCard(bare, dataOf(bare));
    expect(screen.getByRole("group", { name: word })).toBeInTheDocument();
    expect(screen.getByText(word)).toBeInTheDocument();
  });

  it("a later live state wins over a button's answer: cleared, then blocked again", async () => {
    const view = renderCard(CARD);
    await click("Try again");
    expect(await screen.findByText("Cleared: shop.example")).toBeInTheDocument();
    view.rerender(cardView({ ...CARD, state: "blocked", closed_at: CLOSED_AT }));
    expect(screen.getByText("Blocked: shop.example")).toBeInTheDocument();
  });

  it("with no card known it shows the bot's line and no buttons", () => {
    renderCard(undefined);
    expect(screen.getByText(STUCK_LINE)).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("Take control opens the computer panel in control", async () => {
    const Where = () => { const l = useLocation(); return <p data-testid="where">{l.pathname + l.search}</p>; };
    render(
      <MemoryRouter initialEntries={["/chat"]}>
        <StuckCard data={dataOf(CARD)} card={CARD} botName="Scout" tainted={false} />
        <Routes><Route path="*" element={<Where />} /></Routes>
      </MemoryRouter>,
    );
    await click("Take control");
    expect(computer.takeControl).toHaveBeenCalledWith("bot-1");
    expect(screen.getByTestId("where")).toHaveTextContent("/bots/bot-1?panel=computer");
  });
});
