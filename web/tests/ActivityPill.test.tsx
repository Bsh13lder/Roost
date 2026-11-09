import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { ActivityPill } from "../src/components/chat/ActivityPill";
import { COMPUTER_CARD_FOLD_MS } from "../src/components/chat/constants";
import { MessageList } from "../src/components/MessageList";
import type { ActivityRun } from "../src/store/activityRuns";
import type { ComputerRun } from "../src/store/computerRuns";
import type { RunStepOut } from "../src/api/types";
import { initialLiveState } from "../src/store/live";
import { makeBot, makeMessage } from "./fixtures";

// The chat never opens the screen (owner, 2026-10-26): every socket would count here.
const sockets = vi.hoisted(() => ({ opened: 0 }));
vi.mock("../src/hooks/useLiveScreen", () => ({
  useLiveScreen: () => { sockets.opened += 1; return { state: "live", retry: () => {} }; },
}));
vi.mock("../src/hooks/useLiveStore", () => ({ useLiveState: () => initialLiveState() }));
vi.mock("../src/api/computer", () => ({ takeControl: vi.fn() }));
vi.mock("../src/api/desk", () => ({ startBrowser: vi.fn() }));

function step(n: number, over: Partial<RunStepOut> = {}): RunStepOut {
  return {
    bot_id: "bot-1", thread_id: "t-1", run_id: "run-1", step: n, kind: "search",
    line: "Searched the web for “WhatsApp Web”", host: null, at: "2026-10-23T14:05:00+00:00", state: "done", ...over,
  };
}

const RUN: ActivityRun = {
  runId: "run-1", botId: "bot-1", threadId: "t-1", anchorId: "reply-1", order: 1, lastAt: "2026-10-23T14:05:42+00:00",
  steps: [
    step(1, { kind: "think", line: "Thinking" }),
    step(2),
    step(3, { kind: "program", line: "Checked that web.whatsapp.com answers", at: "2026-10-23T14:05:20+00:00", state: "start" }),
  ],
};
const BOT = makeBot({ id: "bot-1", name: "Gela", status: "on_it" });

const show = (live: boolean, run: ActivityRun = RUN, computer?: { run: ComputerRun; live: boolean }) =>
  render(<MemoryRouter><ActivityPill run={run} bot={BOT} live={live} computer={computer}
    technical={["Ran: curl -sI https://web.whatsapp.com | head -n 1 · exit 0"]} /></MemoryRouter>);

afterEach(() => { cleanup(); vi.useRealTimers(); sockets.opened = 0; });

describe("ActivityPill", () => {
  it("while live: what it is doing now in words, its own robot at work and the step count", () => {
    const { container } = show(true);
    const pill = screen.getByTestId("activity-pill");
    expect(within(pill).getByText("Checking that web.whatsapp.com answers…")).toBeInTheDocument();
    expect(within(pill).getByText("2")).toBeInTheDocument();
    const robot = container.querySelector("svg.working-bot");
    expect(robot?.getAttribute("data-moment")).toBe("onit");
    expect(robot?.getAttribute("data-doing")).toBeTruthy();
    expect(container.querySelector(".working-timer")).not.toBeNull();
    expect(container.textContent).not.toContain("curl");
  });

  it("between steps it says Thinking", () => {
    show(true, { ...RUN, steps: RUN.steps.map((s) => ({ ...s, state: "done" as const })) });
    expect(screen.getByText("Thinking…")).toBeInTheDocument();
  });

  it("folds into how long it worked once the run ends", () => {
    vi.useFakeTimers();
    const { rerender } = show(true);
    rerender(<MemoryRouter><ActivityPill run={RUN} bot={{ ...BOT, status: "resting" }} live={false} /></MemoryRouter>);
    act(() => { vi.advanceTimersByTime(COMPUTER_CARD_FOLD_MS + 10); });
    expect(screen.getByTestId("activity-line")).toHaveTextContent("Worked for 42 s · 2 steps");
  });

  it("a tap opens every step in plain words; the code waits under Technical details", async () => {
    show(false);
    await userEvent.click(screen.getByTestId("activity-line"));
    const sheet = await screen.findByRole("dialog");
    expect(within(sheet).getByText("Searched the web for “WhatsApp Web”")).toBeInTheDocument();
    expect(within(sheet).getByText("Checked that web.whatsapp.com answers")).toBeInTheDocument();
    expect(within(sheet).queryByText("Thinking")).not.toBeInTheDocument();
    expect(within(sheet).queryByText(/curl/)).not.toBeInTheDocument();
    await userEvent.click(within(sheet).getByRole("button", { name: "Technical details" }));
    expect(within(sheet).getByText(/curl/)).toBeInTheDocument();
  });

  it("the sheet lists the bot's notes among the steps as quiet sentences, with the Web mark on a tainted one", async () => {
    const run: ActivityRun = {
      ...RUN,
      steps: [
        step(1, { kind: "note", line: "First a fresh search.", tainted: false }),
        step(2),
        step(3, { kind: "note", line: "Found the job; opening its form.", tainted: true }),
      ],
    };
    show(false, run);
    expect(screen.getByTestId("activity-line")).toHaveTextContent("· 1 step");
    await userEvent.click(screen.getByTestId("activity-line"));
    const sheet = await screen.findByRole("dialog");
    const rows = within(sheet).getAllByRole("listitem");
    expect(rows.map((row) => row.textContent)).toEqual([
      expect.stringContaining("First a fresh search."),
      expect.stringContaining("Searched the web for “WhatsApp Web”"),
      expect.stringContaining("Found the job; opening its form."),
    ]);
    expect(rows[0]).toHaveClass("as-step--note");
    expect(within(rows[0]).queryByRole("button", { name: /web content/i })).not.toBeInTheDocument();
    expect(within(rows[2]).getByRole("button", { name: /web content/i })).toBeInTheDocument();
  });

  it("while live, the pill says the bot's newest note", () => {
    show(true, { ...RUN, steps: [...RUN.steps.slice(0, 2), step(3, { kind: "note", line: "Picking the Acme job." }),
      step(4, { kind: "read", line: "Opened upwork.com", state: "start" })] });
    expect(within(screen.getByTestId("activity-pill")).getByText("Picking the Acme job.")).toBeInTheDocument();
  });

  it("holds the same run's computer line under it, with no screen", () => {
    const card: ComputerRun = {
      runId: "run-1", botId: "bot-1", threadId: "t-1", anchorId: "reply-1", order: 1,
      steps: [{ bot_id: "bot-1", thread_id: "t-1", run_id: "run-1", step: 1, kind: "look", line: "Looked at the screen",
        host: "web.whatsapp.com", at: "2026-10-23T14:05:00+00:00" }],
    };
    show(true, RUN, { run: card, live: true });
    expect(within(screen.getByTestId("activity-pill")).getByTestId("computer-card")).toBeInTheDocument();
    expect(screen.getAllByTestId("computer-card")).toHaveLength(1);
    expect(screen.getByText("web.whatsapp.com")).toBeInTheDocument();
    expect(sockets.opened).toBe(0);
  });

  it("the sheet of a run that used the computer lists the steps and offers Open computer, never the screen", async () => {
    show(false, RUN, { run: CARD, live: false });
    await userEvent.click(screen.getByTestId("activity-line"));
    const sheet = await screen.findByRole("dialog");
    expect(within(sheet).getByRole("button", { name: "Open computer" })).toBeInTheDocument();
    expect(within(sheet).getByRole("button", { name: "Take control" })).toBeInTheDocument();
    expect(sheet.querySelector(".cc-screen")).toBeNull();
    expect(sockets.opened).toBe(0);
  });
});

const CARD: ComputerRun = {
  runId: "run-1", botId: "bot-1", threadId: "t-1", anchorId: "reply-1", order: 1,
  steps: [{ bot_id: "bot-1", thread_id: "t-1", run_id: "run-1", step: 1, kind: "look", line: "Looked at the screen",
    host: "web.whatsapp.com", at: "2026-10-23T14:05:00+00:00" }],
};

describe("a finished computer run under a folded pill", () => {
  it("folds to the line alone, newest run included", () => {
    show(false, RUN, { run: CARD, live: false });
    expect(screen.getByTestId("activity-line")).toBeInTheDocument();
    expect(screen.queryByTestId("computer-kept")).not.toBeInTheDocument();
    expect(screen.queryByTestId("computer-card")).not.toBeInTheDocument();
  });

  it("in a chat, every finished computer run is a quiet line and no screen opens", () => {
    const older: ComputerRun = { ...CARD, runId: "run-0", anchorId: "reply-0", order: 0 };
    const olderPill: ActivityRun = { ...RUN, runId: "run-0", anchorId: "reply-0", order: 0 };
    const messages = [
      makeMessage({ id: "reply-0", role: "bot", body: "First.", seq: 1, thread_id: "t-1", author_bot_id: "bot-1" }),
      makeMessage({ id: "reply-1", role: "bot", body: "Done.", seq: 2, thread_id: "t-1", author_bot_id: "bot-1" }),
    ];
    render(<MemoryRouter><MessageList botName="Gela" messages={messages} team={[{ ...BOT, status: "resting" }]}
      activityRuns={{ "run-0": olderPill, "run-1": RUN }} computerRuns={{ "run-0": older, "run-1": CARD }} /></MemoryRouter>);
    expect(screen.getAllByTestId("activity-line")).toHaveLength(2);
    expect(screen.queryByTestId("computer-kept")).not.toBeInTheDocument();
    expect(sockets.opened).toBe(0);
  });
});

describe("a chat with the pill", () => {
  const thread = [
    makeMessage({ id: "u1", role: "user", body: "open WhatsApp", seq: 1, thread_id: "t-1" }),
    makeMessage({ id: "p1", role: "activity", kind: "program_activity", seq: 2, thread_id: "t-1",
      body: JSON.stringify({ command: "curl -sI https://web.whatsapp.com", exit_code: 0 }) }),
    makeMessage({ id: "reply-1", role: "bot", body: "Done.", seq: 3, thread_id: "t-1", author_bot_id: "bot-1" }),
  ];

  it("draws the pill in the reply and keeps program rows and step lines out of the flow", () => {
    render(<MemoryRouter><MessageList botName="Gela" messages={thread} team={[{ ...BOT, status: "resting" }]}
      activityRuns={{ "run-1": RUN }} toolLines={{ "reply-1": ["Ran a program"] }} /></MemoryRouter>);
    expect(screen.getByTestId("activity-line")).toBeInTheDocument();
    expect(document.body.textContent).not.toContain("curl");
    expect(screen.queryByText("Ran a program")).not.toBeInTheDocument();
  });

  it("a run whose reply has settled stays folded when the bot starts its next run", () => {
    render(<MemoryRouter><MessageList botName="Gela" messages={thread} team={[BOT]} activityRuns={{ "run-1": RUN }} /></MemoryRouter>);
    expect(screen.getByTestId("activity-line")).toBeInTheDocument();
    expect(screen.queryByTestId("activity-pill")).not.toBeInTheDocument();
  });

  it("a room (no pill) keeps today's rows", () => {
    render(<MemoryRouter><MessageList botName="Gela" messages={thread} team={[BOT]} /></MemoryRouter>);
    expect(screen.getByText("Ran a program")).toBeInTheDocument();
  });
});
