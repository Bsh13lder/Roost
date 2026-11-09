import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { NewBot } from "../src/pages/NewBot";
import { makeBot } from "./fixtures";

const createBotMock = vi.fn();
const checkMock = vi.fn();
vi.mock("../src/api/bots", () => ({ createBot: (d: unknown) => createBotMock(d) }));
vi.mock("../src/api/templates", () => ({ checkTemplateFile: (f: unknown) => checkMock(f) }));
// Chief wears violet and Scout blue, so a new bot starts in teal.
vi.mock("../src/hooks/useLiveStore", () => ({ useLiveState: () => ({ bots: {
  c: makeBot({ id: "c", name: "Chief", avatar: { shape: "classic", color: "#8b5cf6", badge: "none", screen: "glow" } }),
  s: makeBot({ id: "s", name: "Scout", avatar: { shape: "round", color: "#3B82F6", badge: "none" } }),
} }) }));
vi.mock("../src/hooks/useTemplates", () => ({
  useTemplates: () => ({ error: null, templates: [
    { id: "researcher", label: "Researcher", name: "Researcher", job: "Reads the web", instructions: "Cite pages.",
      avatar: { shape: "wide", color: "#3b82f6", badge: "none" } },
  ] }),
}));

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/bots/new"]}>
      <Routes>
        <Route path="/bots/new" element={<NewBot />} />
        <Route path="/bots/:botId" element={<p>Chat page</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

// Braces: a beforeEach that returns a function has it run as a teardown (it would call the mock).
beforeEach(() => { createBotMock.mockResolvedValue(makeBot({ id: "bot-5" })); });
afterEach(() => { cleanup(); createBotMock.mockReset(); checkMock.mockReset(); });

describe("NewBot", () => {
  it("starts a new bot in a colour no teammate wears", async () => {
    renderPage();
    await userEvent.type(screen.getByLabelText("Name"), "Quill");
    await userEvent.type(screen.getByLabelText("Job"), "Drafts notes");
    await userEvent.click(screen.getByRole("button", { name: "Create bot" }));
    expect(createBotMock).toHaveBeenCalledWith(expect.objectContaining({
      avatar: { shape: "mochi", color: "#14b8a6", badge: "none" },
    }));
  });

  it("a template only fills the form; Create makes the bot", async () => {
    renderPage();
    await userEvent.click(screen.getByRole("button", { name: "Researcher" }));
    expect(screen.getByLabelText("Name")).toHaveValue("Researcher");
    expect(screen.getByLabelText("Instructions")).toHaveValue("Cite pages.");
    expect(createBotMock).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Create bot" }));
    expect(createBotMock).toHaveBeenCalledWith(expect.objectContaining({ name: "Researcher", template_id: "researcher" }));
    expect(createBotMock.mock.calls[0][0]).not.toHaveProperty("roles");
    expect(await screen.findByText("Chat page")).toBeInTheDocument();
  });

  it("From a file only fills the form", async () => {
    checkMock.mockResolvedValue({ name: "Scout", job: "finds prices", instructions: "Be brief.",
      avatar: { shape: "egg", color: "#14b8a6", badge: "none" } });
    renderPage();
    const file = new File([JSON.stringify({ format: "roost-bot" })], "Scout.roost-bot.json", { type: "application/json" });
    await userEvent.upload(screen.getByLabelText("From a file"), file);
    expect(await screen.findByDisplayValue("Scout")).toBeInTheDocument();
    expect(checkMock).toHaveBeenCalledWith({ format: "roost-bot" });
    expect(createBotMock).not.toHaveBeenCalled();
  });

  it("a file that is not JSON says so", async () => {
    renderPage();
    await userEvent.upload(screen.getByLabelText("From a file"), new File(["nope"], "x.json", { type: "application/json" }));
    expect(await screen.findByText("That file is not a Roost bot file (it is not JSON).")).toBeInTheDocument();
  });
});
