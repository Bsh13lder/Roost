import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { SettingsSheet } from "../src/components/settings/SettingsSheet";
import { ACCENT_KEY } from "../src/lib/accent";

const logout = vi.fn();
const listGrants = vi.fn();
const listConnectors = vi.fn();
vi.mock("../src/hooks/useAuth", () => ({ useAuth: () => ({ user: { id: "u", username: "blck it" }, logout }) }));
vi.mock("../src/api/mac", () => ({ listGrants: () => listGrants() }));
vi.mock("../src/api/connectors", () => ({ listConnectors: () => listConnectors() }));
const listPaymentCards = vi.fn();
const deletePaymentCard = vi.fn();
vi.mock("../src/api/payments", () => ({
  listPaymentCards: () => listPaymentCards(), deletePaymentCard: (id: string) => deletePaymentCard(id),
}));
const listVaultPasswords = vi.fn();
vi.mock("../src/api/vaultPasswords", () => ({
  listVaultPasswords: () => listVaultPasswords(), saveVaultPassword: vi.fn(), patchVaultPassword: vi.fn(),
  deleteVaultPassword: vi.fn(),
}));
vi.mock("../src/hooks/useLiveStore", () => ({
  useLiveState: () => ({ bots: { "bot-1": { id: "bot-1", name: "Scout" } }, connectorVersion: 0 }),
}));

const GRANTS = [
  { id: "g1", bot_id: "bot-1", label: "Notes", path: "/Users/me/Notes", access: "read", read_policy: "ask", is_vault: false, created_at: "x" },
  { id: "g2", bot_id: null, label: "Inbox", path: "/Users/me/Inbox", access: "edit", read_policy: "ask", is_vault: false, created_at: "x" },
];

function renderSheet() {
  const onClose = vi.fn();
  render(<MemoryRouter><SettingsSheet open onClose={onClose} /></MemoryRouter>);
  return { onClose, sheet: screen.getByRole("dialog", { name: "Settings" }) };
}

beforeEach(() => {
  listGrants.mockResolvedValue(GRANTS);
  listVaultPasswords.mockResolvedValue([{ id: "l1", host: "upwork.com", username: "me", always: true,
    created_at: "x", updated_at: "x", last_used_at: null }]);
  listPaymentCards.mockResolvedValue([{ id: "c1", brand: "visa", last4: "4242", last_used_at: null }]);
  listConnectors.mockResolvedValue([{ id: "c1", name: "Weather", host: "api.weather.example", key_hint: "key set", bot_ids: ["bot-1"] }]);
});
afterEach(() => {
  cleanup(); logout.mockReset(); listGrants.mockReset(); listConnectors.mockReset(); localStorage.clear();
  delete document.documentElement.dataset.accent;
});

describe("the Settings sheet behind your initials (restructure slice 3)", () => {
  it("is grouped cards: Account, Time zone, Connections, Appearance, Notifications, Version, then Sign out", () => {
    const { sheet } = renderSheet();
    const groups = within(sheet).getAllByRole("region").map((group) => group.getAttribute("aria-label"));
    expect(groups).toEqual(["Account", "Time zone", "Connections", "Appearance", "Notifications", "Version"]);
    expect(within(sheet).getByText("blck it")).toBeInTheDocument();
    expect(within(sheet).getByText("BI")).toBeInTheDocument();
    const buttons = within(sheet).getAllByRole("button");
    expect(buttons[buttons.length - 1]).toHaveTextContent("Sign out");
  });

  it("Connections sums up your connectors and Mac folders", async () => {
    const { sheet } = renderSheet();
    const connections = within(sheet).getByRole("region", { name: "Connections" });
    expect(await within(connections).findByText("1 connector")).toBeInTheDocument();
    expect(await within(connections).findByText("2 folders")).toBeInTheDocument();
  });

  it("the Mac folders row lists every folder with the bot it is for, and Back returns", async () => {
    const { sheet } = renderSheet();
    await userEvent.click(await within(sheet).findByRole("button", { name: /Your Mac: folders/ }));
    expect(within(sheet).getByRole("heading", { level: 3, name: "Your Mac: folders" })).toBeInTheDocument();
    expect(within(sheet).getByText("/Users/me/Notes")).toBeInTheDocument();
    expect(within(sheet).getByText("Scout")).toBeInTheDocument();
    expect(within(sheet).getByText("Every bot")).toBeInTheDocument();
    await userEvent.click(within(sheet).getByRole("button", { name: "Back to Settings" }));
    expect(within(sheet).getByRole("region", { name: "Account" })).toBeInTheDocument();
  });

  it("the Connectors row lists every connector with its site and who may use it", async () => {
    const { sheet } = renderSheet();
    await userEvent.click(await within(sheet).findByRole("button", { name: /^Connectors/ }));
    expect(within(sheet).getByRole("heading", { level: 3, name: "Connectors" })).toBeInTheDocument();
    expect(within(sheet).getByText("Weather")).toBeInTheDocument();
    expect(within(sheet).getByText("api.weather.example · key set")).toBeInTheDocument();
    expect(within(sheet).getByText("Scout")).toBeInTheDocument();
  });

  it("an accent colour applies at once and is remembered in this browser", async () => {
    const { sheet } = renderSheet();
    const accents = within(sheet).getByRole("radiogroup", { name: "Accent colour" });
    expect(within(accents).getAllByRole("radio")).toHaveLength(6);
    expect(within(accents).getByRole("radio", { name: "Violet" })).toBeChecked();
    await userEvent.click(within(accents).getByRole("radio", { name: "Teal" }));
    expect(within(accents).getByRole("radio", { name: "Teal" })).toBeChecked();
    expect(document.documentElement.dataset.accent).toBe("teal");
    expect(localStorage.getItem(ACCENT_KEY)).toBe("teal");
  });

  it("Sign out logs you out", async () => {
    const { sheet } = renderSheet();
    await userEvent.click(within(sheet).getByRole("button", { name: "Sign out" }));
    expect(logout).toHaveBeenCalled();
  });

  it("a failed load of the folders says so instead of a count", async () => {
    listGrants.mockRejectedValue(new Error("down"));
    const { sheet } = renderSheet();
    expect(await within(sheet).findByText("Couldn't load")).toBeInTheDocument();
  });

  it("Vault: cards lists brand and last 4 and deletes a card", async () => {
    deletePaymentCard.mockResolvedValue(undefined);
    render(<SettingsSheet open onClose={() => undefined} />);
    await userEvent.click(await screen.findByRole("button", { name: /Vault: cards/ }));
    expect(screen.getByText("Visa ending 4242")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Delete" }));
    expect(deletePaymentCard).toHaveBeenCalledWith("c1");
    expect(await screen.findByText(/No saved cards/)).toBeInTheDocument();
  });

  it("Vault: passwords counts your logins and lists them with Always, never a password", async () => {
    const { sheet } = renderSheet();
    const connections = within(sheet).getByRole("region", { name: "Connections" });
    expect(await within(connections).findByText("1 login")).toBeInTheDocument();
    await userEvent.click(within(connections).getByRole("button", { name: /Vault: passwords/ }));
    expect(within(sheet).getByRole("heading", { level: 3, name: "Vault: passwords" })).toBeInTheDocument();
    expect(within(sheet).getByText("upwork.com")).toBeInTheDocument();
    expect(within(sheet).getByRole("switch", { name: "Always for this site" })).toHaveAttribute("aria-checked", "true");
    expect(within(sheet).getByRole("button", { name: "Add a login" })).toBeInTheDocument();
  });
});
