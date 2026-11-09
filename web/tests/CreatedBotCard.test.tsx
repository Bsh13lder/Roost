import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { CREATED_CHECKED_TEXT, CreatedBotCard } from "../src/components/CreatedBotCard";
import type { CreatedCardData } from "../src/api/types";
import { makeBot } from "./fixtures";

const deleteBotMock = vi.fn();
vi.mock("../src/api/bots", () => ({ deleteBot: (id: string) => deleteBotMock(id) }));

const CARD: CreatedCardData = {
  bot_id: "bot-7", name: "HiMap Social", job: "Plans HiMap's social posts",
  instructions: "Draft posts for HiMap.", avatar: { shape: "crest", color: "#ec4899", badge: "none" },
};
const TEAM = [makeBot({ id: "bot-7", name: "HiMap Social" })];
const renderCard = (team = TEAM) =>
  render(<MemoryRouter><CreatedBotCard card={CARD} team={team} /></MemoryRouter>);

afterEach(() => { cleanup(); vi.restoreAllMocks(); deleteBotMock.mockReset(); });

describe("CreatedBotCard", () => {
  it("shows the new bot, its full instructions, Open and Undo", () => {
    renderCard();
    const card = screen.getByRole("group", { name: "Created HiMap Social" });
    expect(card).toHaveTextContent("Plans HiMap's social posts");
    expect(card).toHaveTextContent("Draft posts for HiMap.");
    expect(screen.getByRole("link", { name: "Open" })).toHaveAttribute("href", "/bots/bot-7");
  });

  it("a bot made after the chat read web content says it was auto-checked", () => {
    const { unmount } = renderCard();
    expect(screen.queryByText(/Auto-checked/)).not.toBeInTheDocument();
    unmount();
    render(<MemoryRouter><CreatedBotCard card={{ ...CARD, checked: true }} team={TEAM} /></MemoryRouter>);
    expect(screen.getByRole("note")).toHaveTextContent(CREATED_CHECKED_TEXT);
  });

  it("Undo retires the bot after you confirm, then folds to one line", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    deleteBotMock.mockResolvedValue(undefined);
    renderCard();
    await userEvent.click(screen.getByRole("button", { name: "Undo" }));
    expect(deleteBotMock).toHaveBeenCalledWith("bot-7");
    expect(await screen.findByText("Undone: HiMap Social was retired.")).toBeInTheDocument();
  });

  it("a cancelled Undo changes nothing", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(false);
    renderCard();
    await userEvent.click(screen.getByRole("button", { name: "Undo" }));
    expect(deleteBotMock).not.toHaveBeenCalled();
  });

  it("a bot retired elsewhere folds the card", () => {
    renderCard([makeBot({ id: "bot-1", name: "Chief" })]);
    expect(screen.getByText("HiMap Social was retired.")).toBeInTheDocument();
  });
});
