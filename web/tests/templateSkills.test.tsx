import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { NewBot } from "../src/pages/NewBot";
import { makeBot } from "./fixtures";

const createBotMock = vi.fn();
const checkMock = vi.fn();
const importMock = vi.fn();
vi.mock("../src/api/bots", () => ({ createBot: (d: unknown) => createBotMock(d) }));
vi.mock("../src/api/templates", () => ({ checkTemplateFile: (f: unknown) => checkMock(f) }));
vi.mock("../src/api/skills", () => ({ importSkills: (...a: unknown[]) => importMock(...a) }));
vi.mock("../src/hooks/useLiveStore", () => ({ useLiveState: () => ({ bots: {} }) }));
vi.mock("../src/hooks/useTemplates", () => ({ useTemplates: () => ({ error: null, templates: [] }) }));

const FILE = {
  name: "Scout", job: "finds prices", instructions: "Be brief.",
  avatar: { shape: "egg", color: "#14b8a6", badge: "none" },
  skills: [
    { name: "Post on X", use_when: "posting", body: "1. Open X", have: false },
    { name: "Weekly SEO", use_when: "on Mondays", body: "1. Check rankings", have: false },
    { name: "Mine already", use_when: "always", body: "1. x", have: true },
  ],
};

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

async function loadFileAndCreate() {
  renderPage();
  await userEvent.upload(screen.getByLabelText("From a file"),
    new File([JSON.stringify({ format: "roost-bot" })], "scout.roost-bot.json", { type: "application/json" }));
  expect(await screen.findByText("This file has 3 skills")).toBeInTheDocument();
  expect(importMock).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole("button", { name: "Create bot" }));
  expect(await screen.findByText("Add its skills?")).toBeInTheDocument();
}

beforeEach(() => {
  createBotMock.mockResolvedValue(makeBot({ id: "bot-5" }));
  checkMock.mockResolvedValue(FILE);
  importMock.mockResolvedValue({ added: [], have: [] });
});
afterEach(() => { cleanup(); createBotMock.mockReset(); checkMock.mockReset(); importMock.mockReset(); });

describe("Add its skills?", () => {
  it("New bot shows the file's skills and adds only the ticked ones after Create", async () => {
    await loadFileAndCreate();
    const have = screen.getByRole("checkbox", { name: /Mine already/ });
    expect(have).toBeDisabled();
    expect(have).not.toBeChecked();
    expect(screen.getByText("You already have this one")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("checkbox", { name: /Weekly SEO/ }));
    await userEvent.click(screen.getByRole("button", { name: "Add skills" }));
    expect(importMock).toHaveBeenCalledWith([{ name: "Post on X", use_when: "posting", steps: "1. Open X" }], "bot-5");
    expect(await screen.findByText("Chat page")).toBeInTheDocument();
  });

  it("Skip adds nothing", async () => {
    await loadFileAndCreate();
    await userEvent.click(screen.getByRole("button", { name: "Skip" }));
    expect(importMock).not.toHaveBeenCalled();
    await waitFor(() => expect(screen.getByText("Chat page")).toBeInTheDocument());
  });

  it("a file without skills goes straight to the bot", async () => {
    checkMock.mockResolvedValue({ ...FILE, skills: [] });
    renderPage();
    await userEvent.upload(screen.getByLabelText("From a file"),
      new File([JSON.stringify({ format: "roost-bot" })], "scout.roost-bot.json", { type: "application/json" }));
    await waitFor(() => expect(screen.getByLabelText("Name")).toHaveValue("Scout"));
    await userEvent.click(screen.getByRole("button", { name: "Create bot" }));
    expect(await screen.findByText("Chat page")).toBeInTheDocument();
  });
});
