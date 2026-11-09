// B3 (docs/plans/2026-10-23-roost-tabs-signin-flow.md): the Sign-in card's masked field. You type your password or
// code in the chat; it goes straight into the box on the bot's computer, and the field forgets it at once.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { StuckCard } from "../src/components/StuckCard";
import { parseStuckMessage } from "../src/lib/stuck";
import { ApiError } from "../src/api/client";
import type { StuckMessageData } from "../src/api/types";
import { makeStuckCard } from "./fixtures";

const computer = { getControl: vi.fn(), takeControl: vi.fn() };
const stuck = { clearStuck: vi.fn(), openSignIn: vi.fn(), laterStuck: vi.fn(), typeSecret: vi.fn() };
vi.mock("../src/api/computer", () => ({
  getControl: (id: string) => computer.getControl(id),
  takeControl: (id: string) => computer.takeControl(id),
}));
vi.mock("../src/api/stuck", () => ({
  clearStuck: (...a: unknown[]) => stuck.clearStuck(...a),
  openSignIn: (id: string) => stuck.openSignIn(id),
  laterStuck: (id: string) => stuck.laterStuck(id),
  typeSecret: (...a: unknown[]) => stuck.typeSecret(...a),
}));

const SECRET = "Tr0ub4dor&3";
const CARD = makeStuckCard({ sign_in: true, secret_field: "password" });
const DATA: StuckMessageData = {
  card_id: CARD.id, bot_id: CARD.bot_id, reason: "login", host: CARD.host, url: CARD.url, note: "",
  suggest_main_browser: false, line: "Type your shop.example password here.", sign_in: true, secret_field: "password",
};
const renderCard = (data = DATA, card = CARD) => render(
  <MemoryRouter><StuckCard data={data} card={card} botName="Gela" tainted /></MemoryRouter>,
);
const field = () => screen.getByLabelText("Your shop.example password") as HTMLInputElement;

beforeEach(() => {
  computer.getControl.mockResolvedValue({ held: false, since: null });
  stuck.typeSecret.mockResolvedValue({ ...CARD, state: "cleared", closed_at: "2026-10-23T10:00:00Z" });
});
afterEach(() => { cleanup(); [...Object.values(computer), ...Object.values(stuck)].forEach((m) => m.mockReset()); });

describe("the Sign-in card's secret field", () => {
  it("reads the field kind from the message body, only on a sign-in card", () => {
    expect(parseStuckMessage(JSON.stringify(DATA))?.secret_field).toBe("password");
    expect(parseStuckMessage(JSON.stringify({ ...DATA, secret_field: "pin" }))?.secret_field).toBeUndefined();
    expect(parseStuckMessage(JSON.stringify({ ...DATA, sign_in: false }))?.secret_field).toBeUndefined();
  });

  it("says where it goes and that the bot never sees it, with a masked field, Take control and Later", () => {
    renderCard();
    const card = screen.getByRole("group", { name: "Sign in on shop.example" });
    expect(card).toHaveTextContent(
      "Type your shop.example password; it goes straight into the box on Gela's computer. The bot never sees it.");
    expect(field()).toHaveAttribute("type", "password");
    expect(field()).toHaveAttribute("autocomplete", "off");
    expect(field()).toHaveAttribute("maxlength", "256");
    expect(screen.getByRole("button", { name: "Take control" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Later" })).toBeEnabled();
    expect(screen.queryByRole("button", { name: "Check again" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
  });

  it("sends the value once, empties the field at once, and folds when the card is cleared", async () => {
    renderCard();
    await userEvent.type(field(), SECRET);
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(stuck.typeSecret).toHaveBeenCalledTimes(1);
    expect(stuck.typeSecret).toHaveBeenCalledWith(CARD.id, SECRET, true);
    expect(await screen.findByText("Cleared: shop.example")).toBeInTheDocument();
    expect(document.body.innerHTML).not.toContain(SECRET);
  });

  it("a refusal is said on the card, the field is empty and the card stays open", async () => {
    stuck.typeSecret.mockRejectedValue(new ApiError(409, "There's no password or code box on the page any more, so nothing was typed."));
    renderCard();
    await userEvent.type(field(), `${SECRET}{Enter}`);
    expect(await screen.findByText(/no password or code box/)).toBeInTheDocument();
    expect(field().value).toBe("");
    expect(document.body.innerHTML).not.toContain(SECRET);
  });

  it("a code card asks for the code", () => {
    renderCard({ ...DATA, secret_field: "code" }, { ...CARD, secret_field: "code" });
    expect(screen.getByLabelText("Your shop.example code")).toBeInTheDocument();
  });

  it("a password card offers Save in Vault, on by default, and sends what you chose", async () => {
    renderCard();
    const save = screen.getByRole("checkbox", { name: "Save in Vault" });
    expect(save).toBeChecked();
    await userEvent.click(save);
    await userEvent.type(field(), `${SECRET}{Enter}`);
    expect(stuck.typeSecret).toHaveBeenCalledWith(CARD.id, SECRET, false);
  });

  it("a code card has no Save in Vault and never asks to save", async () => {
    renderCard({ ...DATA, secret_field: "code" }, { ...CARD, secret_field: "code" });
    expect(screen.queryByRole("checkbox", { name: "Save in Vault" })).not.toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Your shop.example code"), "123456{Enter}");
    expect(stuck.typeSecret).toHaveBeenCalledWith(CARD.id, "123456", false);
  });
});
