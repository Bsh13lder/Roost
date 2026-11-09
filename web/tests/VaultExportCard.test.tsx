import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import VaultExportCard, { resultLine } from "../src/components/vaultExport/VaultExportCard";
import type { VaultExportOut } from "../src/api/vaultExport";

const api = { getVaultExport: vi.fn(), putVaultExport: vi.fn(), runVaultExport: vi.fn(), setProjectExport: vi.fn() };
vi.mock("../src/api/vaultExport", () => ({
  getVaultExport: (...a: unknown[]) => api.getVaultExport(...a),
  putVaultExport: (...a: unknown[]) => api.putVaultExport(...a),
  runVaultExport: (...a: unknown[]) => api.runVaultExport(...a),
  setProjectExport: (...a: unknown[]) => api.setProjectExport(...a),
}));

const settings = (over: Partial<VaultExportOut> = {}): VaultExportOut => ({
  grant_id: "g1", journals: false, grants: [{ id: "g1", label: "Vault", bot_id: null, is_vault: true }],
  projects: [], last: { result: null, written: 0, conflicts: 0, at: null }, ...over,
});

beforeEach(() => {
  api.getVaultExport.mockResolvedValue(settings());
  api.setProjectExport.mockResolvedValue({ project_id: "p1", on: true });
  api.putVaultExport.mockImplementation((grant: string | null, journals: boolean) =>
    Promise.resolve(settings({ grant_id: grant, journals, projects: ["p1"] })));
  api.runVaultExport.mockResolvedValue({ result: "ok", written: 4, conflicts: 1, failed: 0 });
});
afterEach(() => { cleanup(); Object.values(api).forEach((fn) => fn.mockReset()); });

describe("VaultExportCard", () => {
  it("starts off and turning it on shows the folder, journals and Export now", async () => {
    render(<VaultExportCard projectId="p1" />);
    const toggle = await screen.findByRole("switch", { name: "Export to my vault" });
    expect(toggle).toHaveAttribute("aria-checked", "false");
    expect(screen.queryByRole("button", { name: "Export now" })).not.toBeInTheDocument();
    await userEvent.click(toggle);
    expect(api.setProjectExport).toHaveBeenCalledWith("p1", true);
    expect(await screen.findByRole("button", { name: "Export now" })).toBeInTheDocument();
    expect(screen.getByRole("switch", { name: "Export journals" })).toHaveAttribute("aria-checked", "false");
  });

  it("Export now shows the result in words", async () => {
    api.getVaultExport.mockResolvedValue(settings({ projects: ["p1"] }));
    render(<VaultExportCard projectId="p1" />);
    await userEvent.click(await screen.findByRole("button", { name: "Export now" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Exported. 4 written, 1 kept as you edited them");
  });

  it("Export journals saves the setting", async () => {
    api.getVaultExport.mockResolvedValue(settings({ projects: ["p1"] }));
    render(<VaultExportCard projectId="p1" />);
    await userEvent.click(await screen.findByRole("switch", { name: "Export journals" }));
    expect(api.putVaultExport).toHaveBeenCalledWith("g1", true);
    await waitFor(() => expect(screen.getByRole("switch", { name: "Export journals" })).toHaveAttribute("aria-checked", "true"));
  });

  it("asks for a shared folder when there is none", async () => {
    api.getVaultExport.mockResolvedValue(settings({ grants: [], grant_id: null, projects: ["p1"] }));
    render(<VaultExportCard projectId="p1" />);
    expect(await screen.findByText(/Share a folder first/)).toBeInTheDocument();
  });

  it("shows an error it could not load", async () => {
    api.getVaultExport.mockRejectedValue(new Error("down"));
    render(<VaultExportCard projectId="p1" />);
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });

  it("resultLine words each code", () => {
    expect(resultLine(null, 0, 0)).toBeNull();
    expect(resultLine("partial", 2, 0)).toBe("Exported part of it; the rest follows in a minute. 2 written.");
    expect(resultLine("no_grant", 0, 0)).toBe("That folder is gone or read-only. Choose another.");
  });
});
