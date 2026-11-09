import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { NewModelBanner } from "../src/components/NewModelBanner";
import { resetModelsCache } from "../src/lib/models";
import { makeBot } from "./fixtures";

function stub(notice: { id: string; label: string } | null) {
  const calls: string[] = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    calls.push(`${init?.method ?? "GET"} ${url}`);
    if (init?.method === "POST") return new Response(null, { status: 204 });
    return new Response(JSON.stringify({ choices: [], efforts: [], default_model: "x", default_effort: {}, notice }), { status: 200 });
  }));
  return calls;
}

const show = () => render(<MemoryRouter><NewModelBanner bots={[makeBot({ id: "b1", name: "Scout" })]} /></MemoryRouter>);

afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); resetModelsCache(); window.localStorage.clear(); });

const expand = async () => userEvent.click(await screen.findByRole("button", { name: "Show new model" }));

describe("NewModelBanner", () => {
  it("shows nothing without a notice", async () => {
    const calls = stub(null);
    show();
    await waitFor(() => expect(calls.length).toBe(1));
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("the banner names the model and Try it lists your bots", async () => {
    stub({ id: "new-id", label: "Opus 5.6" });
    show();
    expect(await screen.findByText(/New model: Opus 5.6/)).toBeInTheDocument();
    await expand();
    await userEvent.click(screen.getByRole("button", { name: "Try it" }));
    expect(await screen.findByRole("menuitem", { name: "Scout" })).toHaveAttribute("href", "/bots/b1?panel=settings&try=new-id");
  });

  it("Dismiss calls the dismiss route and hides it", async () => {
    const calls = stub({ id: "new-id", label: "Opus 5.6" });
    show();
    await expand();
    await userEvent.click(await screen.findByRole("button", { name: "Dismiss" }));
    expect(screen.queryByText(/New model/)).toBeNull();
    expect(calls).toContain("POST /api/models/notice/new-id/dismiss");
  });

  it("starts as one compact row with a chevron, the Try it menu folded away", async () => {
    stub({ id: "new-id", label: "Opus 5.6" });
    show();
    const toggle = await screen.findByRole("button", { name: "Show new model" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByRole("status")).toHaveClass("model-banner--folded");
    expect(screen.queryByRole("button", { name: "Try it" })).toBeNull();
    expect(screen.queryByText(/try it on a bot/)).toBeNull();
  });

  it("remembers in this browser that you opened it", async () => {
    stub({ id: "new-id", label: "Opus 5.6" });
    show();
    await expand();
    expect(screen.getByRole("button", { name: "Hide new model" })).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("button", { name: "Try it" })).toBeInTheDocument();
    cleanup();
    show();
    expect(await screen.findByRole("button", { name: "Hide new model" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Hide new model" }));
    cleanup();
    show();
    expect(await screen.findByRole("button", { name: "Show new model" })).toBeInTheDocument();
  });

  it("still works, folded, when the browser refuses site data", async () => {
    stub({ id: "new-id", label: "Opus 5.6" });
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("blocked"); });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("blocked"); });
    vi.spyOn(console, "warn").mockImplementation(() => undefined);
    show();
    await expand();
    expect(screen.getByRole("button", { name: "Try it" })).toBeInTheDocument();
  });
});
