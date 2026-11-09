import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { ChatList } from "../src/components/ChatList";
import type { BotOut, ChatRowOut } from "../src/api/types";
import { makeBot } from "./fixtures";

const setPinned = vi.fn();
vi.mock("../src/api/bots", () => ({ setPinned: (id: string, v: boolean) => setPinned(id, v) }));

const NOW = new Date("2026-10-14T12:30:00Z");
const ROWS: ChatRowOut[] = [
  { kind: "bot", id: "bot-1", name: "Scout", thread_id: "t-1", preview: "The market opens at 9:00.",
    preview_kind: "text", from_you: false, last_at: "2026-10-14T12:19:00Z", tainted: false },
  { kind: "room", id: "room-1", name: "Saturday", thread_id: "t-9", preview: "Chief → Scout: price a basket",
    preview_kind: "handoff", from_you: false, last_at: "2026-10-13T08:00:00Z", tainted: false },
  { kind: "bot", id: "bot-2", name: "Ledger", thread_id: null, preview: null, preview_kind: null,
    from_you: false, last_at: "2026-10-04T10:00:00Z", tainted: false },
];
const BOTS: Record<string, BotOut> = {
  "bot-1": makeBot({ id: "bot-1", name: "Scout" }),
  "bot-2": makeBot({ id: "bot-2", name: "Ledger" }),
};

function renderList(props: Partial<Parameters<typeof ChatList>[0]> = {}, path = "/") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <ChatList rows={ROWS} bots={BOTS} query="" attention={new Set()} now={NOW} {...props} />
    </MemoryRouter>,
  );
}

afterEach(cleanup);

describe("ChatList", () => {
  it("shows every chat with its preview and time, linking to the bot or the room", () => {
    renderList();
    const hrefs = screen.getAllByRole("link").map((link) => link.getAttribute("href"));
    expect(hrefs).toEqual(["/bots/bot-1", "/rooms/room-1", "/bots/bot-2"]);
    expect(screen.getByText("The market opens at 9:00.")).toBeInTheDocument();
    expect(screen.getByText("14:19")).toBeInTheDocument();
    expect(screen.getByText("Yesterday")).toBeInTheDocument();
    expect(screen.getByText("No messages yet")).toBeInTheDocument();
  });

  it("a renamed bot shows (and is found by) its new name at once", () => {
    renderList({ bots: { ...BOTS, "bot-1": makeBot({ id: "bot-1", name: "Scout Two" }) }, query: "two" });
    expect(screen.getByText("Scout Two")).toBeInTheDocument();
    expect(screen.queryByText("Ledger")).not.toBeInTheDocument();
  });

  it("search filters by name and by preview", () => {
    renderList({ query: "market" });
    expect(screen.getAllByRole("link")).toHaveLength(1);
    cleanup();
    renderList({ query: "LEDG" });
    expect(screen.getByRole("link")).toHaveAttribute("href", "/bots/bot-2");
    cleanup();
    renderList({ query: "nothing like this" });
    expect(screen.getByText("No chats match.")).toBeInTheDocument();
  });

  it("a bot with a picture still shows Off duty in the list, in its ghost's posture", () => {
    const avatar = { shape: "classic", color: "#10b981", badge: "none", screen: "glow", picture: "/api/bots/bot-2/picture?v=0123456789ab" } as const;
    renderList({ bots: { ...BOTS, "bot-2": makeBot({ id: "bot-2", name: "Ledger", status: "off_duty", off_duty: true, avatar }) } });
    const row = screen.getByRole("link", { name: /Ledger/ });
    expect(row.querySelector("image.robot__picture")).not.toBeNull();
    expect(row.querySelector("svg.avatar")?.getAttribute("data-moment")).toBe("off");
    expect(row.querySelectorAll(".robot__eye")).toHaveLength(0); // the picture, with no eyes on it
    // The other bot has no picture: its eyes show.
    expect(screen.getByRole("link", { name: /^Scout/ }).querySelectorAll(".robot__eye")).toHaveLength(2);
  });

  it("a busy bot shows its status line with the activity instead of the preview", () => {
    renderList({ bots: { ...BOTS, "bot-1": makeBot({ id: "bot-1", name: "Scout", status: "on_it", activity: "opening elpais.com" }) } });
    expect(screen.getByText("On it · opening elpais.com")).toBeInTheDocument();
    expect(screen.queryByText("The market opens at 9:00.")).not.toBeInTheDocument();
  });

  it("your own last message reads You:, and a bot that needs you is highlighted", () => {
    renderList({ rows: [{ ...ROWS[0], from_you: true, preview: "hello" }], attention: new Set(["bot-1"]) });
    expect(screen.getByText("You: hello")).toBeInTheDocument();
    expect(screen.getByRole("listitem")).toHaveClass("chat-row--attention");
  });
});

describe("ChatList (redesign P2)", () => {
  const CHIEF = makeBot({ id: "bot-9", name: "Chief", is_primary: true });
  const WITH_CHIEF: ChatRowOut[] = [...ROWS, { kind: "bot", id: "bot-9", name: "Chief", thread_id: null, preview: null,
    preview_kind: null, from_you: false, last_at: "2026-10-01T10:00:00Z", tainted: false }];

  it("leaves the main bot to the robot row and lists every other chat newest first", () => {
    renderList({ rows: WITH_CHIEF, bots: { ...BOTS, "bot-9": CHIEF } });
    const links = screen.getAllByRole("link");
    expect(links.map((link) => link.getAttribute("href"))).toEqual(["/bots/bot-1", "/rooms/room-1", "/bots/bot-2"]);
    expect(links[0].querySelector(".robot__star")).toBeNull();
  });

  it("shows a preview as plain words, never the reply's markdown", () => {
    renderList({ rows: [{ ...ROWS[0], preview: "**Booked** [the table](https://x.example/t) for [[Saturday]]." }] });
    expect(screen.getByText("Booked the table for Saturday.")).toBeInTheDocument();
  });

  it("dots a chat with a message you have not seen", () => {
    renderList({ unread: new Set(["bot-1"]) });
    expect(within(screen.getByRole("link", { name: /^Scout\b/ })).getByText("Unread")).toBeInTheDocument();
    expect(screen.getAllByText("Unread")).toHaveLength(1);
  });

  it("marks the open chat's row, and each ghost shows its bot's status", () => {
    const busy = makeBot({ id: "bot-1", name: "Scout", status: "on_it", activity: "opening elpais.com" });
    renderList({ bots: { ...BOTS, "bot-1": busy } }, "/bots/bot-2");
    expect(screen.getByRole("link", { name: /^Ledger\b/ })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: /^Scout\b/ }).querySelector("svg.avatar")).toHaveAttribute("data-moment", "onit");
    expect(screen.getByRole("link", { name: /^Ledger\b/ }).querySelector("svg.avatar")).toHaveAttribute("data-moment", "rest");
  });

  it("draws a nav of sections, a labelled bot under its heading", () => {
    renderList({ bots: { ...BOTS, "bot-2": makeBot({ id: "bot-2", name: "Ledger", group: "Money" }) } });
    const nav = screen.getByRole("navigation", { name: "Chats" });
    expect(within(nav).getByRole("heading", { name: "Money" })).toBeInTheDocument();
    const money = within(nav).getByRole("region", { name: "Money" });
    expect(within(money).getByRole("link")).toHaveAttribute("href", "/bots/bot-2");
  });

  it("a bot's row has a menu with Pin; a room's row has none", async () => {
    setPinned.mockResolvedValue(makeBot({ id: "bot-1", pinned: true }));
    renderList();
    expect(screen.getAllByRole("button", { name: /menu$/ })).toHaveLength(2);
    await userEvent.click(screen.getByRole("button", { name: "Scout menu" }));
    await userEvent.click(screen.getByRole("menuitem", { name: "Pin" }));
    expect(setPinned).toHaveBeenCalledWith("bot-1", true);
  });
});

describe("ChatList when every bot is pinned", () => {
  const CHIEF = makeBot({ id: "bot-9", name: "Chief", is_primary: true });
  const PINNED = makeBot({ id: "bot-1", name: "Scout", pinned: true });
  const ONLY_PINNED: ChatRowOut[] = [
    { ...ROWS[0] },
    { kind: "bot", id: "bot-9", name: "Chief", thread_id: null, preview: null, preview_kind: null, from_you: false,
      last_at: "2026-10-01T10:00:00Z", tainted: false },
  ];

  it("never says No chats yet when the bots are all up in the robot row", () => {
    renderList({ rows: ONLY_PINNED, bots: { "bot-9": CHIEF, "bot-1": PINNED } });
    expect(screen.queryByText("No chats yet.")).toBeNull();
    expect(screen.queryAllByRole("link")).toHaveLength(0);
  });

  it("says No chats yet only when there are no bots and no rooms at all", () => {
    renderList({ rows: [], bots: {} });
    expect(screen.getByText("No chats yet.")).toBeInTheDocument();
  });
});
