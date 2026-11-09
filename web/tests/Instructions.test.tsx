import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { Instructions } from "../src/pages/Instructions";
import { makeBot } from "./fixtures";

const updateBotMock = vi.fn();
vi.mock("../src/api/bots", () => ({
  getBot: () => Promise.resolve(makeBot({ id: "bot-1", instructions: "Be brief." })),
  updateBot: (id: string, patch: unknown) => updateBotMock(id, patch),
}));

function Landed() {
  const { pathname, search } = useLocation();
  return <p>{`Landed ${pathname}${search}`}</p>;
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/bots/bot-1/instructions"]}>
      <Routes>
        <Route path="/bots/:botId/instructions" element={<Instructions />} />
        <Route path="/bots/:botId" element={<Landed />} />
      </Routes>
    </MemoryRouter>,
  );
}

afterEach(() => { cleanup(); updateBotMock.mockReset(); });

describe("Instructions page", () => {
  it("Save stays disabled until the text changes, then saves and goes back", async () => {
    updateBotMock.mockResolvedValue(makeBot());
    renderPage();
    const box = await screen.findByRole("textbox", { name: "Instructions" });
    expect(box).toHaveValue("Be brief.");
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
    await userEvent.type(box, " Cite sources.");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(updateBotMock).toHaveBeenCalledWith("bot-1", { instructions: "Be brief. Cite sources." });
    expect(await screen.findByText("Landed /bots/bot-1?panel=settings")).toBeInTheDocument();
  });

  it("shows the counter near the limit and never sends an over-limit draft", async () => {
    renderPage();
    const box = await screen.findByRole("textbox", { name: "Instructions" });
    expect(screen.queryByText(/\/ 4000/)).not.toBeInTheDocument();
    await userEvent.clear(box);
    await userEvent.click(box);
    await userEvent.paste("x".repeat(4005));
    expect(screen.getByText("5 characters over the limit — shorten it to save.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
    expect(updateBotMock).not.toHaveBeenCalled();
  });

  it("Back goes to the open profile panel", async () => {
    renderPage();
    await screen.findByRole("textbox", { name: "Instructions" });
    await userEvent.click(screen.getByRole("link", { name: "Back" }));
    expect(await screen.findByText("Landed /bots/bot-1?panel=settings")).toBeInTheDocument();
  });
});
