import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SiteLogins } from "../src/components/computer/SiteLogins";

const vault = { listSiteLogins: vi.fn(), forgetSiteLogin: vi.fn() };
vi.mock("../src/api/vault", () => ({
  listSiteLogins: (id: string) => vault.listSiteLogins(id),
  forgetSiteLogin: (id: string, loginId: string) => vault.forgetSiteLogin(id, loginId),
}));

const LOGIN = { id: "l-1", bot_id: "bot-1", host: "shop.example", label: "work email", updated_at: "2026-10-21T10:00:00Z" };
beforeEach(() => { vault.forgetSiteLogin.mockResolvedValue(undefined); });
afterEach(() => { cleanup(); Object.values(vault).forEach((m) => m.mockReset()); });

describe("SiteLogins", () => {
  it("lists sign-ins and forgets one", async () => {
    vault.listSiteLogins.mockResolvedValue([LOGIN]);
    render(<SiteLogins botId="bot-1" />);
    expect(await screen.findByText("shop.example · work email")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Vault: site logins" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Forget/ }));
    expect(vault.forgetSiteLogin).toHaveBeenCalledWith("bot-1", "l-1");
    expect(await screen.findByText("No sign-ins saved yet.")).toBeInTheDocument();
  });

  it("says when nothing is saved and when the list fails", async () => {
    vault.listSiteLogins.mockResolvedValue([]);
    render(<SiteLogins botId="bot-1" />);
    expect(await screen.findByText("No sign-ins saved yet.")).toBeInTheDocument();
    cleanup();
    vault.listSiteLogins.mockRejectedValue(new Error("x"));
    render(<SiteLogins botId="bot-1" />);
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});
