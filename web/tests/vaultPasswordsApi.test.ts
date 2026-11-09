// Vault: passwords (docs/plans/2026-11-08-roost-vault-passwords.md): the four routes, and Save in Vault on the
// Sign-in card's masked field.
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  deleteVaultPassword, listVaultPasswords, patchVaultPassword, saveVaultPassword,
} from "../src/api/vaultPasswords";
import { typeSecret } from "../src/api/stuck";

const fetchMock = vi.fn();
afterEach(() => { fetchMock.mockReset(); vi.unstubAllGlobals(); });

function called(): { method: string; url: string; body: unknown } {
  const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
  return { method: init.method ?? "GET", url, body: init.body ? JSON.parse(init.body as string) : undefined };
}

const reply = (status: number, body: unknown = {}) => new Response(
  status === 204 ? null : JSON.stringify(body), { status },
);

describe("the Vault: passwords api", () => {
  it("lists, saves, patches and deletes logins", async () => {
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockImplementation(async () => reply(200, []));
    await listVaultPasswords();
    expect(called()).toMatchObject({ method: "GET", url: "/api/vault/passwords" });
    fetchMock.mockReset().mockImplementation(async () => reply(201));
    await saveVaultPassword({ host: "upwork.com", username: "me", password: "pw" });
    expect(called()).toEqual({
      method: "POST", url: "/api/vault/passwords", body: { host: "upwork.com", username: "me", password: "pw" },
    });
    fetchMock.mockReset().mockImplementation(async () => reply(200));
    await patchVaultPassword("l 1", { always: true });
    expect(called()).toEqual({ method: "PATCH", url: "/api/vault/passwords/l%201", body: { always: true } });
    fetchMock.mockReset().mockImplementation(async () => reply(204));
    await deleteVaultPassword("l1");
    expect(called()).toMatchObject({ method: "DELETE", url: "/api/vault/passwords/l1" });
  });

  it("the masked field sends save with its value", async () => {
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockImplementation(async () => reply(200));
    await typeSecret("card-1", "pw", true);
    expect(called()).toEqual({ method: "POST", url: "/api/stuck/card-1/secret", body: { value: "pw", save: true } });
    fetchMock.mockReset().mockImplementation(async () => reply(200));
    await typeSecret("card-1", "123456");
    expect(called().body).toEqual({ value: "123456", save: false });
  });
});
