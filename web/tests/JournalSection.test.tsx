import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import JournalSection, { journalBody } from "../src/components/journal/JournalSection";

const api = { listJournalDays: vi.fn(), readJournalDay: vi.fn() };
vi.mock("../src/api/journal", () => ({
  listJournalDays: (...a: unknown[]) => api.listJournalDays(...a),
  readJournalDay: (...a: unknown[]) => api.readJournalDay(...a),
}));

const CONTENT = '---\ntags: ["roost/journal", "bot/ana"]\nday: "2026-10-22"\n---\n# Ana · 2026-10-22\n\n- 14:19 Added a task\n';

beforeEach(() => {
  api.listJournalDays.mockResolvedValue([
    { day: "2026-10-22", entries: 2, tainted: false, updated_at: "x" },
    { day: "2026-10-21", entries: 1, tainted: false, updated_at: "x" },
  ]);
  api.readJournalDay.mockResolvedValue({
    day: "2026-10-22", entries: 1, tainted: true, updated_at: "x", bot_id: "bot-1", content: CONTENT,
  });
});
afterEach(() => { cleanup(); api.listJournalDays.mockReset(); api.readJournalDay.mockReset(); });

describe("JournalSection", () => {
  it("lists the recent days with their entry counts", async () => {
    render(<JournalSection botId="bot-1" />);
    expect(await screen.findByText("2026-10-22")).toBeInTheDocument();
    expect(screen.getByText("2 entries")).toBeInTheDocument();
    expect(screen.getByText("1 entry")).toBeInTheDocument();
    expect(api.listJournalDays).toHaveBeenCalledWith("bot-1");
  });

  it("opens a day read-only, without its front matter, and goes back", async () => {
    render(<JournalSection botId="bot-1" />);
    await userEvent.click(await screen.findByRole("button", { name: /2026-10-22/ }));
    expect(api.readJournalDay).toHaveBeenCalledWith("bot-1", "2026-10-22");
    expect(await screen.findByText(/Added a task/)).toBeInTheDocument();
    expect(screen.queryByText(/roost\/journal/)).not.toBeInTheDocument();
    expect(screen.getByText("Some entries came after reading web content.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "All days" }));
    expect(await screen.findByText("2026-10-21")).toBeInTheDocument();
  });

  it("says when the journal is empty, and shows an error", async () => {
    api.listJournalDays.mockResolvedValue([]);
    render(<JournalSection botId="bot-1" />);
    expect(await screen.findByText("Nothing in the journal yet.")).toBeInTheDocument();
    cleanup();
    api.listJournalDays.mockRejectedValue(new Error("down"));
    render(<JournalSection botId="bot-1" />);
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });

  it("journalBody drops only the front matter", () => {
    expect(journalBody(CONTENT)).toBe("# Ana · 2026-10-22\n\n- 14:19 Added a task\n");
    expect(journalBody("plain")).toBe("plain");
  });
});
