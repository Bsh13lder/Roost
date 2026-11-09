import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AppsList } from "../src/components/computer/AppsList";

const apps = { listApps: vi.fn(), removeApp: vi.fn() };
vi.mock("../src/api/apps", () => ({
  listApps: (id: string) => apps.listApps(id),
  removeApp: (id: string, appId: string) => apps.removeApp(id, appId),
}));

const GIMP = { id: "a-1", package: "gimp", installed_at: "2026-10-22T10:00:00Z" };
afterEach(() => { cleanup(); Object.values(apps).forEach((m) => m.mockReset()); });

// Install an app: the packages the owner said Yes to, each with Remove (the owner's own click, no card).
describe("AppsList", () => {
  it("lists the apps and removes one", async () => {
    apps.listApps.mockResolvedValue([GIMP]);
    apps.removeApp.mockResolvedValue(undefined);
    render(<AppsList botId="bot-1" />);
    expect(await screen.findByText("gimp")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Apps" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Remove gimp" }));
    expect(apps.removeApp).toHaveBeenCalledWith("bot-1", "a-1");
    expect(await screen.findByText("No apps installed yet.")).toBeInTheDocument();
  });

  it("loads again when its reload key changes, so an app just installed shows", async () => {
    apps.listApps.mockResolvedValue([]);
    const view = render(<AppsList botId="bot-1" reloadKey="on_it" />);
    expect(await screen.findByText("No apps installed yet.")).toBeInTheDocument();
    apps.listApps.mockResolvedValue([GIMP]);
    view.rerender(<AppsList botId="bot-1" reloadKey="resting" />);
    expect(await screen.findByText("gimp")).toBeInTheDocument();
  });

  it("keeps the row and says why when Remove fails", async () => {
    apps.listApps.mockResolvedValue([GIMP]);
    apps.removeApp.mockRejectedValue(new Error("The computer couldn't be reached"));
    render(<AppsList botId="bot-1" />);
    await userEvent.click(await screen.findByRole("button", { name: "Remove gimp" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getByText("gimp")).toBeInTheDocument();
  });
});
