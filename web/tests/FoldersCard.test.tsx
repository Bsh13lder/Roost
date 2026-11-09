import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { FoldersCard } from "../src/components/profile/FoldersCard";
import { ApiError } from "../src/api/client";
import type { GrantOut } from "../src/api/types";
import { makeBot } from "./fixtures";

const mac = { listGrants: vi.fn(), addGrant: vi.fn(), pickFolder: vi.fn(), revokeGrant: vi.fn() };
vi.mock("../src/api/mac", () => ({
  listGrants: (id?: string) => mac.listGrants(id), addGrant: (b: unknown) => mac.addGrant(b),
  pickFolder: () => mac.pickFolder(), revokeGrant: (id: string) => mac.revokeGrant(id),
}));
afterEach(() => { cleanup(); Object.values(mac).forEach((m) => m.mockReset()); });

const grant = (over: Partial<GrantOut> = {}): GrantOut => ({
  id: "g1", bot_id: "bot-1", label: "MySpace", path: "/Users/me/MySpace", access: "read_write",
  read_policy: "ask_each", is_vault: false, created_at: "x", ...over,
});

describe("FoldersCard", () => {
  it("lists this bot's and all bots' folders, all-bots locked", async () => {
    mac.listGrants.mockResolvedValue([grant(), grant({ id: "g2", bot_id: null, label: "Shared", path: "/Users/me/Shared", access: "read" })]);
    render(<FoldersCard bot={makeBot()} />);
    expect(await screen.findByText("MySpace")).toBeInTheDocument();
    expect(mac.listGrants).toHaveBeenCalledWith("bot-1");
    expect(screen.getByText("/Users/me/MySpace")).toBeInTheDocument();
    expect(screen.getByText("Read and write")).toBeInTheDocument();
    expect(screen.getByText("Read only")).toBeInTheDocument();
    expect(screen.getByText("All bots")).toBeInTheDocument();
    expect(screen.getAllByText("Reads: Ask every time")).toHaveLength(2);
  });

  it("shows an empty state", async () => {
    mac.listGrants.mockResolvedValue([]);
    render(<FoldersCard bot={makeBot()} />);
    expect(await screen.findByText("No folders yet.")).toBeInTheDocument();
  });

  it("Add folder saves a typed path", async () => {
    mac.listGrants.mockResolvedValue([]);
    mac.addGrant.mockResolvedValue(grant());
    render(<FoldersCard bot={makeBot()} />);
    await userEvent.click(await screen.findByRole("button", { name: "Add folder" }));
    await userEvent.type(screen.getByLabelText("Path"), "/Users/me/MySpace");
    await userEvent.type(screen.getByLabelText("Label"), "MySpace");
    await userEvent.click(screen.getByRole("button", { name: "Read and write" }));
    await userEvent.click(screen.getByRole("button", { name: "Ask once per session" }));
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(mac.addGrant).toHaveBeenCalledWith({
      path: "/Users/me/MySpace", label: "MySpace", access: "read_write", read_policy: "ask_session", bot_id: "bot-1",
    });
    expect(await screen.findByText("MySpace")).toBeInTheDocument();
  });

  it("All bots sends no bot id", async () => {
    mac.listGrants.mockResolvedValue([]);
    mac.addGrant.mockResolvedValue(grant({ bot_id: null }));
    render(<FoldersCard bot={makeBot()} />);
    await userEvent.click(await screen.findByRole("button", { name: "Add folder" }));
    await userEvent.type(screen.getByLabelText("Path"), "/Users/me/Docs");
    await userEvent.click(screen.getByRole("button", { name: "All bots" }));
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(mac.addGrant).toHaveBeenCalledWith(expect.objectContaining({ bot_id: null, label: "Docs", access: "read" }));
  });

  it("Choose folder fills the path, and a cancel changes nothing", async () => {
    mac.listGrants.mockResolvedValue([]);
    render(<FoldersCard bot={makeBot()} />);
    await userEvent.click(await screen.findByRole("button", { name: "Add folder" }));
    mac.pickFolder.mockResolvedValueOnce({ path: "/Users/me/Picked" });
    await userEvent.click(screen.getByRole("button", { name: "Choose folder…" }));
    expect(await screen.findByDisplayValue("/Users/me/Picked")).toBeInTheDocument();
    mac.pickFolder.mockResolvedValueOnce({ path: null });
    await userEvent.click(screen.getByRole("button", { name: "Choose folder…" }));
    expect(screen.getByDisplayValue("/Users/me/Picked")).toBeInTheDocument();
  });

  it("a refused folder shows the server's words", async () => {
    mac.listGrants.mockResolvedValue([]);
    mac.addGrant.mockRejectedValue(new ApiError(422, "That folder holds keys, so it can't be shared."));
    render(<FoldersCard bot={makeBot()} />);
    await userEvent.click(await screen.findByRole("button", { name: "Add folder" }));
    await userEvent.type(screen.getByLabelText("Path"), "/Users/me/.ssh");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("That folder holds keys, so it can't be shared.")).toBeInTheDocument();
  });

  it("Revoke asks first and removes the row", async () => {
    mac.listGrants.mockResolvedValue([grant()]);
    mac.revokeGrant.mockResolvedValue(undefined);
    render(<FoldersCard bot={makeBot()} />);
    await userEvent.click(await screen.findByRole("button", { name: "Revoke MySpace" }));
    expect(mac.revokeGrant).not.toHaveBeenCalled();
    const confirm = screen.getByRole("dialog", { name: "Stop sharing MySpace?" });
    await userEvent.click(within(confirm).getByRole("button", { name: "Revoke" }));
    expect(mac.revokeGrant).toHaveBeenCalledWith("g1");
    await vi.waitFor(() => expect(screen.queryByText("MySpace")).not.toBeInTheDocument());
    expect(screen.getByText("No folders yet.")).toBeInTheDocument();
  });
});
