// Vault: passwords (docs/plans/2026-11-08-roost-vault-passwords.md V2, V3): Settings' list and the Save a password
// sheet, shared with the chat composer's + menu. No password is ever shown, and the sheet forgets it after a send.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { VaultPasswordsList } from "../src/components/settings/VaultPasswordsList";
import { SavePasswordSheet } from "../src/components/vault/SavePasswordSheet";
import { ComposerPlus } from "../src/components/chat/ComposerPlus";
import { ToastProvider } from "../src/ui/Toast";
import { ApiError } from "../src/api/client";
import type { VaultPasswordOut } from "../src/api/vaultPasswords";

const api = { list: vi.fn(), save: vi.fn(), patch: vi.fn(), remove: vi.fn() };
vi.mock("../src/api/vaultPasswords", () => ({
  listVaultPasswords: () => api.list(),
  saveVaultPassword: (body: unknown) => api.save(body),
  patchVaultPassword: (id: string, body: unknown) => api.patch(id, body),
  deleteVaultPassword: (id: string) => api.remove(id),
}));
vi.mock("../src/api/documents", () => ({ uploadPdf: vi.fn() }));

const SECRET = "Tr0ub4dor&3";
const LOGIN: VaultPasswordOut = {
  id: "l1", host: "upwork.com", username: "me@example.com", always: false,
  created_at: "2026-11-08T09:00:00Z", updated_at: "2026-11-08T09:00:00Z", last_used_at: "2026-11-08T13:19:00Z",
};
const NEW_LOGIN: VaultPasswordOut = { ...LOGIN, id: "l2", host: "shop.example", username: "", last_used_at: null };

const renderList = (logins: readonly VaultPasswordOut[] = [LOGIN]) =>
  render(<ToastProvider><VaultPasswordsList logins={logins} /></ToastProvider>);

async function fillSheet(host: string, username: string, password: string) {
  const sheet = screen.getByRole("dialog", { name: "Save a password" });
  await userEvent.type(within(sheet).getByLabelText("Site"), host);
  if (username) await userEvent.type(within(sheet).getByLabelText("User name"), username);
  await userEvent.type(within(sheet).getByLabelText("Password"), password);
  return sheet;
}

beforeEach(() => { api.save.mockResolvedValue(NEW_LOGIN); });
afterEach(() => { cleanup(); Object.values(api).forEach((mock) => mock.mockReset()); vi.restoreAllMocks(); });

describe("Settings → Vault: passwords", () => {
  it("lists each login by site, user name and last use on the account clock, never a password", () => {
    renderList();
    expect(screen.getByText("upwork.com")).toBeInTheDocument();
    expect(screen.getByText("me@example.com · Last used 8 Nov, 14:19")).toBeInTheDocument();
    expect(screen.getByText(/Roost keeps these sealed. Your bots never see them/)).toBeInTheDocument();
    expect(screen.getByRole("switch", { name: "Always for this site" })).toHaveAttribute("aria-checked", "false");
    expect(document.querySelector("input[type='password']")).toBeNull();
  });

  it("says so when nothing is saved", () => {
    renderList([]);
    expect(screen.getByText("No saved passwords yet.")).toBeInTheDocument();
  });

  it("the switch PATCHes always and shows what the server kept", async () => {
    api.patch.mockResolvedValue({ ...LOGIN, always: true });
    renderList();
    await userEvent.click(screen.getByRole("switch", { name: "Always for this site" }));
    expect(api.patch).toHaveBeenCalledWith("l1", { always: true });
    expect(await screen.findByRole("switch", { name: "Always for this site" })).toHaveAttribute("aria-checked", "true");
  });

  it("a failed switch says why and stays as it was", async () => {
    api.patch.mockRejectedValue(new ApiError(404, "That login isn't in Vault: passwords."));
    renderList();
    await userEvent.click(screen.getByRole("switch", { name: "Always for this site" }));
    expect(await screen.findByText("That login isn't in Vault: passwords.")).toBeInTheDocument();
    expect(screen.getByRole("switch", { name: "Always for this site" })).toHaveAttribute("aria-checked", "false");
  });

  it("Delete asks first, then removes the login", async () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValueOnce(false).mockReturnValueOnce(true);
    api.remove.mockResolvedValue(undefined);
    renderList();
    await userEvent.click(screen.getByRole("button", { name: "Delete" }));
    expect(confirm).toHaveBeenCalledWith(expect.stringContaining("upwork.com"));
    expect(api.remove).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Delete" }));
    expect(api.remove).toHaveBeenCalledWith("l1");
    expect(await screen.findByText("No saved passwords yet.")).toBeInTheDocument();
  });

  it("Add a login opens the sheet, posts the body, lists the new login and toasts", async () => {
    renderList();
    await userEvent.click(screen.getByRole("button", { name: "Add a login" }));
    const sheet = await fillSheet("shop.example", "", SECRET);
    const password = within(sheet).getByLabelText("Password");
    expect(password).toHaveAttribute("type", "password");
    expect(password).toHaveAttribute("autocomplete", "new-password");
    await userEvent.click(within(sheet).getByRole("button", { name: "Save" }));
    expect(api.save).toHaveBeenCalledWith({ host: "shop.example", username: "", password: SECRET });
    expect(await screen.findByText("Saved in Vault: passwords")).toBeInTheDocument();
    expect(screen.getByText("shop.example")).toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: "Save a password" })).not.toBeInTheDocument();
    expect(document.body.innerHTML).not.toContain(SECRET);
  });
});

describe("the Save a password sheet", () => {
  it("a 422 shows the server's words and empties the password, keeping the site", async () => {
    api.save.mockRejectedValue(new ApiError(422, "Those login details don't fit. Check the site, user name and password."));
    render(<SavePasswordSheet open onOpenChange={() => undefined} />);
    const sheet = await fillSheet("not a site", "me", SECRET);
    await userEvent.click(within(sheet).getByRole("button", { name: "Save" }));
    expect(await within(sheet).findByText(/Those login details don't fit/)).toBeInTheDocument();
    expect((within(sheet).getByLabelText("Password") as HTMLInputElement).value).toBe("");
    expect((within(sheet).getByLabelText("Site") as HTMLInputElement).value).toBe("not a site");
    expect(document.body.innerHTML).not.toContain(SECRET);
  });

  it("Save waits for a site and a password; Cancel closes without posting", async () => {
    const onOpenChange = vi.fn();
    render(<SavePasswordSheet open onOpenChange={onOpenChange} />);
    const sheet = screen.getByRole("dialog", { name: "Save a password" });
    expect(within(sheet).getByRole("button", { name: "Save" })).toBeDisabled();
    await userEvent.type(within(sheet).getByLabelText("Password"), SECRET);
    expect(within(sheet).getByRole("button", { name: "Save" })).toBeDisabled();
    await userEvent.click(within(sheet).getByRole("button", { name: "Cancel" }));
    expect(onOpenChange).toHaveBeenCalledWith(false);
    expect(api.save).not.toHaveBeenCalled();
  });
});

describe("the chat composer's + menu", () => {
  it("Save a password opens the sheet, which posts only to the Vault", async () => {
    const onAdded = vi.fn();
    render(<ToastProvider><ComposerPlus onAdded={onAdded} onError={() => undefined} /></ToastProvider>);
    await userEvent.click(screen.getByRole("button", { name: "Add to the chat" }));
    await userEvent.click(await screen.findByRole("menuitem", { name: "Save a password" }));
    const sheet = await fillSheet("upwork.com", "me@example.com", SECRET);
    await userEvent.click(within(sheet).getByRole("button", { name: "Save" }));
    expect(api.save).toHaveBeenCalledWith({ host: "upwork.com", username: "me@example.com", password: SECRET });
    expect(await screen.findByText("Saved in Vault: passwords")).toBeInTheDocument();
    expect(onAdded).not.toHaveBeenCalled();
  });
});
