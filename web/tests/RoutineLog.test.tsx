import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { RoutineLog } from "../src/pages/RoutineLog";
import { makeBot, makeMessage } from "./fixtures";
import { routine } from "./routineFixtures";

const api = { listRoutines: vi.fn(), listMessages: vi.fn() };
vi.mock("../src/api/routines", () => ({ listRoutines: (...a: unknown[]) => api.listRoutines(...a) }));
vi.mock("../src/api/threads", () => ({ listMessages: (...a: unknown[]) => api.listMessages(...a) }));
vi.mock("../src/hooks/useLiveStore", () => ({
  useLiveState: () => ({ bots: { "bot-1": makeBot() }, messagesByThread: {} }),
}));

beforeEach(() => {
  api.listRoutines.mockResolvedValue([routine()]);
  api.listMessages.mockResolvedValue([
    makeMessage({ id: "m-1", role: "user", kind: "routine", body: "Read the news.\n\nPlanned 10:07, running now.", seq: 1 }),
    makeMessage({ id: "m-2", author_bot_id: "bot-1", body: "Three new emails.", seq: 2 }),
  ]);
});
afterEach(() => { cleanup(); Object.values(api).forEach((mock) => mock.mockReset()); });

const view = () => render(
  <MemoryRouter initialEntries={["/bots/bot-1/routines/r-1/log"]}>
    <Routes><Route path="/bots/:botId/routines/:routineId/log" element={<RoutineLog />} /></Routes>
  </MemoryRouter>,
);

describe("RoutineLog", () => {
  it("the run log is read-only", async () => {
    view();
    expect(await screen.findByText("Three new emails.")).toBeInTheDocument();
    expect(api.listMessages).toHaveBeenCalledWith("t-log");
    expect(screen.getByText(/Planned 10:07, running now\./)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Morning digest · run log" })).toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Send/ })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to the chat" })).toHaveAttribute("href", "/bots/bot-1");
  });

  it("says so when the routine is not there", async () => {
    api.listRoutines.mockResolvedValue([]);
    view();
    expect(await screen.findByText("That routine isn't here any more.")).toBeInTheDocument();
  });
});
