import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { SuggestionCard } from "../src/components/SuggestionCard";
import { ApiError } from "../src/api/client";
import { makeBot } from "./fixtures";

const createBotMock = vi.fn();
vi.mock("../src/api/bots", () => ({ createBot: (...args: unknown[]) => createBotMock(...args) }));

const LEDGER = { name: "Ledger", job: "Keeps the books", avatar: { shape: "wide" as const, color: "#3b82f6", badge: "finance" as const } };

// Block body on purpose: a beforeEach that returns a function has it run
// as teardown, which would call the (rejecting) mock after the test.
beforeEach(() => {
  createBotMock.mockReset();
});
afterEach(() => cleanup());

function renderCard(team = [makeBot({ name: "Chief" })], tainted = false) {
  render(<MemoryRouter><SuggestionCard suggestion={LEDGER} team={team} tainted={tainted} /></MemoryRouter>);
}

describe("SuggestionCard", () => {
  it("creates the bot only when clicked, through the normal create API, then folds", async () => {
    createBotMock.mockResolvedValue(makeBot({ id: "new", name: "Ledger" }));
    renderCard();
    expect(createBotMock).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Create this bot" }));
    expect(createBotMock).toHaveBeenCalledWith({
      name: "Ledger", job: "Keeps the books", instructions: "", avatar: { ...LEDGER.avatar, badge: "none" },
    });
    expect(await screen.findByText("Created Ledger")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open" })).toHaveAttribute("href", "/bots/new");
  });

  it("tells the rest of the page the team changed once the bot exists", async () => {
    createBotMock.mockResolvedValue(makeBot({ id: "new", name: "Ledger" }));
    const heard = vi.fn();
    window.addEventListener("roost:team-changed", heard);
    renderCard();
    await userEvent.click(screen.getByRole("button", { name: "Create this bot" }));
    await screen.findByRole("link", { name: "Open" });
    window.removeEventListener("roost:team-changed", heard);
    expect(heard).toHaveBeenCalledOnce();
  });

  it("links to the bot when it is already on the team", () => {
    renderCard([makeBot({ id: "ledger-id", name: "Ledger" })]);
    expect(screen.getByText("Created Ledger")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open" })).toHaveAttribute("href", "/bots/ledger-id");
    expect(screen.queryByRole("button", { name: "Create this bot" })).not.toBeInTheDocument();
  });

  it("shows the reason and keeps the button when creating fails", async () => {
    createBotMock.mockRejectedValue(new ApiError(409, "A bot named 'Ledger' already exists."));
    renderCard();
    await userEvent.click(screen.getByRole("button", { name: "Create this bot" }));
    expect(await screen.findByText("A bot named 'Ledger' already exists.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create this bot" })).toBeEnabled();
  });

  it("warns when the run that suggested it read outside content", () => {
    renderCard(undefined, true);
    expect(screen.getByRole("note")).toHaveTextContent("This run read outside content.");
  });

  it("shows no warning for a clean run", () => {
    renderCard();
    expect(screen.queryByText("This run read outside content.")).not.toBeInTheDocument();
  });
});
