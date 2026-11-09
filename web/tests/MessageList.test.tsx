import { describe, expect, it, vi, afterEach, beforeEach } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { MessageList } from "../src/components/MessageList";
import { makeBot, makeMessage, makeStuckCard, stuckBody, STUCK_LINE } from "./fixtures";
import type { AvatarOut, MessageOut } from "../src/api/types";

// An open Stuck card asks who holds the bot's computer when it mounts; nobody does here.
vi.mock("../src/api/computer", () => ({ getControl: () => Promise.resolve({ held: false, since: null }) }));

const AVATAR: AvatarOut = { shape: "round", color: "#10b981", badge: "none" };

function message(id: string, role: MessageOut["role"], body: string): MessageOut {
  return { id, thread_id: "t-1", role, body, tainted: false, seq: 1, created_at: "x" };
}

const scrollIntoView = vi.fn();

beforeEach(() => {
  scrollIntoView.mockReset();
  Element.prototype.scrollIntoView = scrollIntoView;
});

afterEach(() => cleanup());

describe("MessageList", () => {
  it("invites the first message when the thread is empty", () => {
    render(<MessageList messages={[]} botName="Scout" botAvatar={AVATAR} />);
    expect(screen.getByText(/say hello to scout/i)).toBeInTheDocument();
  });

  it("puts the bot's avatar next to its messages and none next to yours", () => {
    const { container } = render(
      <MessageList
        messages={[message("m-1", "user", "hi"), message("m-2", "bot", "hello there")]}
        botName="Scout"
        botAvatar={AVATAR}
      />,
    );
    expect(container.querySelector(".message--bot svg.avatar")).not.toBeNull();
    expect(container.querySelector(".message--user svg.avatar")).toBeNull();
  });

  it("draws activity lines centred and quiet, with no dot", () => {
    const { container } = render(<MessageList messages={[message("a-1", "activity", "opened example.com")]} botName="Scout" />);
    expect(screen.getByText("opened example.com").closest("li")).toHaveClass("message--activity");
    expect(container.querySelector(".message__activity-dot")).toBeNull();
  });

  it("puts an english_fix line right under the message of yours it names, and an orphan where it stands", () => {
    const fix = (id: string, target: string) => makeMessage({
      id, role: "activity", kind: "english_fix", seq: 3,
      body: JSON.stringify({ message_id: target, said: "I goed home", corrected: "I went home", fixes: [{ wrong: "goed", right: "went" }] }),
    });
    const { container } = render(<MessageList botName="Scout" messages={[
      makeMessage({ id: "u1", role: "user", body: "I goed home", seq: 1 }),
      makeMessage({ id: "b1", role: "bot", body: "Welcome back.", seq: 2 }),
      fix("f1", "u1"),
      fix("f2", "not-loaded"),
    ]} />);
    const rows = [...container.querySelectorAll("li.message")].map((row) => row.getAttribute("data-message-id"));
    expect(rows).toEqual(["u1", "f1", "b1", "f2"]);
    expect(screen.getAllByText("goed")[0].tagName).toBe("DEL");
  });

  it("draws the New line as a separator named New messages", () => {
    render(<MessageList botName="Scout" newAfter="2026-10-14T09:30:00Z" messages={[
      makeMessage({ id: "a", role: "user", created_at: "2026-10-14T09:00:00Z" }),
      makeMessage({ id: "b", created_at: "2026-10-14T10:00:00Z", body: "fresh reply" }),
    ]} />);
    const line = screen.getByRole("separator", { name: "New messages" });
    expect(line).toHaveTextContent("New");
    expect(line.nextElementSibling).toHaveTextContent("fresh reply");
  });

  it("separates the days", () => {
    render(<MessageList botName="Scout" messages={[
      makeMessage({ id: "a", created_at: "2026-10-13T09:00:00Z" }),
      makeMessage({ id: "b", created_at: "2026-10-13T10:00:00Z" }),
      makeMessage({ id: "c", created_at: "2026-10-14T09:00:00Z" }),
    ]} />);
    expect(screen.getAllByRole("separator")).toHaveLength(2);
  });

  it("scrolls to the newest message when one arrives", () => {
    const { rerender } = render(<MessageList messages={[message("m-1", "user", "hi")]} botName="Scout" />);
    scrollIntoView.mockReset();

    rerender(
      <MessageList messages={[message("m-1", "user", "hi"), message("m-2", "bot", "hello")]} botName="Scout" />,
    );

    expect(scrollIntoView).toHaveBeenCalled();
  });
});

describe("MessageList teamwork rows", () => {
  const CHIEF = makeBot({ id: "chief", name: "Chief" });
  const SCOUT = makeBot({ id: "scout", name: "Scout" });

  it("renders a handoff as a line, not a bubble", () => {
    render(<MessageList messages={[makeMessage({ role: "activity", kind: "handoff", body: "Chief → Scout: find hours" })]} botName="Chief" />);
    expect(screen.getByText("Chief → Scout: find hours").closest("li")).toHaveClass("message--handoff");
  });

  it("renders notices quietly and the daily limit with its own style", () => {
    render(
      <MessageList
        messages={[
          makeMessage({ id: "n1", role: "system", kind: "dropped", body: "Stopped." }),
          makeMessage({ id: "n2", role: "system", kind: "daily_limit", body: "Daily limit reached: Scout has done 100 runs today." }),
        ]}
        botName="Scout"
      />,
    );
    expect(screen.getByText("Stopped.").closest("li")).toHaveClass("message--notice");
    expect(screen.getByText(/Daily limit reached/).closest("li")).toHaveClass("message--notice-daily_limit");
  });

  it("names each bot message by its author when a team is given", () => {
    render(
      <MessageList
        messages={[makeMessage({ id: "a", author_bot_id: "chief", body: "plan" }), makeMessage({ id: "b", author_bot_id: "scout", body: "price" })]}
        botName="Room"
        team={[CHIEF, SCOUT]}
      />,
    );
    expect(screen.getByText("plan").closest("li")).toHaveTextContent("Chief");
    expect(screen.getByText("price").closest("li")).toHaveTextContent("Scout");
  });

  it("renders a suggestion card", () => {
    const body = JSON.stringify({ name: "Ledger", job: "Keeps the books", avatar: { shape: "wide", color: "#3b82f6", badge: "finance" } });
    render(<MemoryRouter><MessageList messages={[makeMessage({ kind: "suggestion", body })]} botName="Chief" team={[CHIEF]} /></MemoryRouter>);
    expect(screen.getByRole("button", { name: "Create this bot" })).toBeInTheDocument();
  });
});

describe("MessageList Stuck cards", () => {
  const CARD = makeStuckCard();
  const STUCK = makeMessage({ id: "s-1", kind: "stuck", author_bot_id: "bot-1", body: stuckBody(CARD) });

  it("renders a Stuck card with its buttons while its card is open", () => {
    render(
      <MemoryRouter>
        <MessageList messages={[STUCK]} botName="Scout" team={[makeBot()]} stuck={{ [CARD.id]: CARD }} />
      </MemoryRouter>,
    );
    expect(screen.getByRole("group", { name: "Stuck on shop.example" })).toHaveTextContent(STUCK_LINE);
    expect(screen.getByRole("button", { name: "Take control" })).toBeInTheDocument();
  });

  it("folds a Stuck card once its card is closed", () => {
    render(
      <MemoryRouter>
        <MessageList messages={[STUCK]} botName="Scout" stuck={{ [CARD.id]: { ...CARD, state: "given_up" } }} />
      </MemoryRouter>,
    );
    expect(screen.getByRole("group", { name: "Stopped: shop.example" })).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("a stuck message whose body is not a card stays plain text", () => {
    render(<MessageList messages={[makeMessage({ kind: "stuck", body: "not a card" })]} botName="Scout" />);
    expect(screen.getByText("not a card")).toBeInTheDocument();
  });

  it("your continue line is your own bubble", () => {
    const body = "I cleared the block on shop.example. Read the page again and carry on with: book a table";
    render(<MessageList messages={[makeMessage({ role: "user", kind: "card_answer", body })]} botName="Scout" />);
    expect(screen.getByText(body).closest("li")).toHaveClass("message--user");
  });
});

describe("MessageList while a bot works (redesign P2)", () => {
  const PLACEHOLDER = makeMessage({ id: "r-1", author_bot_id: "bot-1", body: "", seq: 0 });
  const steps = () => within(screen.getByRole("list", { name: "Steps" })).getAllByRole("listitem").map((li) => li.textContent);

  it("shows the bot's own robot at work with what it is doing before any text, never an empty bubble", () => {
    const { container } = render(
      <MessageList messages={[makeMessage({ id: "u", role: "user", body: "plan my week" }), PLACEHOLDER]} botName="Scout" botAvatar={AVATAR} />,
    );
    const typing = screen.getByRole("status", { name: "Scout: Reading your message…" });
    expect(typing.querySelector("svg.working-bot")).toHaveAttribute("data-moment", "onit");
    expect(container.querySelector('[data-message-id="r-1"] svg.avatar')).toBeNull();   // one robot, in the line
    expect(container.querySelector('[data-message-id="r-1"] .message__body')).toBeNull();
  });

  it("an 'On it' first line is the robot's words while it works, and never part of the answer", () => {
    const { container, rerender } = render(
      <MessageList messages={[PLACEHOLDER]} streaming={{ "r-1": "On it: checking your week." }} botName="Scout" botAvatar={AVATAR} />,
    );
    expect(screen.getByRole("status", { name: "Scout: Checking your week…" })).toBeInTheDocument();
    expect(container.querySelector(".message__body")).toBeNull();
    rerender(<MessageList messages={[{ ...PLACEHOLDER, seq: 2, body: "On it: checking your week.\n\nThree things are due." }]}
      botName="Scout" botAvatar={AVATAR} />);
    expect(container.querySelector(".message__body")).toHaveTextContent("Three things are due.");
    expect(container.textContent).not.toContain("On it");
  });

  it("shows a caret while the text streams, and none once the reply is in", () => {
    const { container, rerender } = render(
      <MessageList messages={[PLACEHOLDER]} streaming={{ "r-1": "Here is" }} botName="Scout" botAvatar={AVATAR} />,
    );
    expect(screen.queryByRole("status")).toBeNull();
    expect(container.querySelector(".message__body")).toHaveClass("message__body--streaming");
    expect(container.querySelector(".message__body")).toHaveAttribute("aria-busy", "true");
    rerender(<MessageList messages={[{ ...PLACEHOLDER, seq: 2, body: "Here is the plan." }]} botName="Scout" botAvatar={AVATAR} />);
    expect(container.querySelector(".message__body")).not.toHaveClass("message__body--streaming");
  });

  it("lists what the bot did as compact lines: the current step while it works, all past once the reply is in", () => {
    const lines = { "r-1": ["adding a task", "saving a note"] };
    const { rerender } = render(<MessageList messages={[PLACEHOLDER]} toolLines={lines} botName="Scout" botAvatar={AVATAR} />);
    expect(steps()).toEqual(["Added a task", "Saving a note…"]);
    rerender(<MessageList messages={[{ ...PLACEHOLDER, seq: 2, body: "Done." }]} toolLines={lines} botName="Scout" botAvatar={AVATAR} />);
    expect(steps()).toEqual(["Added a task", "Saved a note"]);
  });

  // Final-review fix: a step is done once the reply's words start to stream after it, not only once the
  // reply settles; a step the bot starts after some words is current until more words come.
  it("finishes the last step as soon as the reply's text streams after it", () => {
    const list = (streaming: Record<string, string>, lines: string[]) => (
      <MessageList messages={[PLACEHOLDER]} streaming={streaming} toolLines={{ "r-1": lines }} botName="Scout" botAvatar={AVATAR} />
    );
    const { container, rerender } = render(list({}, ["adding a task"]));
    expect(steps()).toEqual(["Adding a task…"]);
    rerender(list({ "r-1": "Added" }, ["adding a task"]));
    expect(steps()).toEqual(["Added a task"]);
    expect(container.querySelector(".tool-line--current, .tool-line__spinner")).toBeNull();
    rerender(list({ "r-1": "Added it." }, ["adding a task", "saving a note"]));
    expect(steps()).toEqual(["Added a task", "Saving a note…"]);
    rerender(list({ "r-1": "Added it. Saved" }, ["adding a task", "saving a note"]));
    expect(steps()).toEqual(["Added a task", "Saved a note"]);
  });

  it("shows only the last few steps of a long run, with a count of the earlier ones", () => {
    const lines = { "r-1": ["opening a.example", "reading a.example", "opening b.example", "reading b.example", "opening c.example", "reading c.example", "adding a task"] };
    render(<MessageList messages={[{ ...PLACEHOLDER, seq: 2, body: "Done." }]} toolLines={lines} botName="Scout" botAvatar={AVATAR} />);
    expect(steps()).toEqual(["2 earlier steps", "Opened b.example", "Read b.example", "Opened c.example", "Read c.example", "Added a task"]);
  });
});
