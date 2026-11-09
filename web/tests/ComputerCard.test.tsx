import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { ComputerCard, foldedLine } from "../src/components/chat/ComputerCard";
import { COMPUTER_CARD_FOLD_MS } from "../src/components/chat/constants";
import type { ComputerRun } from "../src/store/computerRuns";
import type { ComputerStepOut } from "../src/api/types";
import { initialLiveState } from "../src/store/live";
import { makeBot } from "./fixtures";

// The chat never shows the screen (owner, 2026-10-26): any socket the card or its sheet opened would count here.
const screenState = vi.hoisted(() => ({ opened: 0 }));
const takeControl = vi.hoisted(() => vi.fn(() => Promise.resolve({ held: true, since: null })));
const navigate = vi.hoisted(() => vi.fn());

vi.mock("../src/hooks/useLiveScreen", () => ({
  useLiveScreen: () => { screenState.opened += 1; return { state: "live", retry: () => {} }; },
}));
vi.mock("../src/hooks/useLiveStore", () => ({ useLiveState: () => initialLiveState() }));
vi.mock("../src/api/computer", () => ({ takeControl }));
vi.mock("react-router-dom", async (original) => ({
  ...(await original<typeof import("react-router-dom")>()), useNavigate: () => navigate,
}));

function step(n: number, over: Partial<ComputerStepOut> = {}): ComputerStepOut {
  return {
    bot_id: "bot-1", thread_id: "t-1", run_id: "run-1", step: n, kind: "click", line: `Clicked 'Item ${n}'`,
    host: "www.upwork.com", at: "2026-10-23T14:05:00+00:00", ...over,
  };
}

const RUN: ComputerRun = {
  runId: "run-1", botId: "bot-1", threadId: "t-1", anchorId: "reply-1", order: 1,
  steps: [step(1, { kind: "look", line: "Looked at the screen" }), step(2), step(3, { kind: "type", line: "Typed into 'Search' (5 characters)" })],
};
const BOT = makeBot({ id: "bot-1", name: "Chief", status: "on_it" });

function show(live: boolean, run: ComputerRun = RUN) {
  return render(<MemoryRouter><ComputerCard run={run} bot={BOT} live={live} /></MemoryRouter>);
}

afterEach(() => { cleanup(); vi.useRealTimers(); screenState.opened = 0; navigate.mockReset(); takeControl.mockClear(); });

describe("ComputerCard", () => {
  it("while live: one compact line with the site, the newest step and its number, and no screen", () => {
    const { container } = show(true);
    const card = screen.getByTestId("computer-card");
    expect(within(card).getByText("www.upwork.com")).toBeInTheDocument();
    expect(within(card).getByText("Typed into 'Search' (5 characters)")).toBeInTheDocument();
    expect(within(card).getByText("Step 3")).toBeInTheDocument();
    expect(within(card).queryByText("Live")).toBeNull();
    expect(container.querySelector(".cc-screen, .cc__screen")).toBeNull();
    expect(screenState.opened).toBe(0);
    expect(screen.getByRole("button", { name: /Chief’s computer on www.upwork.com/ })).toBeInTheDocument();
  });

  it("a run with no step yet says it is getting ready", () => {
    show(true, { ...RUN, steps: [] });
    expect(screen.getByText("Getting ready")).toBeInTheDocument();
  });

  it("folds into one quiet line when the run ends", () => {
    vi.useFakeTimers();
    const { rerender, container } = show(true);
    rerender(<MemoryRouter><ComputerCard run={RUN} bot={BOT} live={false} /></MemoryRouter>);
    expect(container.querySelector(".cc--folding")).not.toBeNull();
    act(() => { vi.advanceTimersByTime(COMPUTER_CARD_FOLD_MS); });
    expect(screen.queryByTestId("computer-card")).toBeNull();
    expect(screen.getByRole("button", { name: /Used its computer · www.upwork.com · 3 steps/ })).toBeInTheDocument();
  });

  it("the folded line says one step, and leaves out a missing site", () => {
    expect(foldedLine({ ...RUN, steps: [step(1, { host: null })] })).toBe("Used its computer · 1 step");
  });

  it("a tap opens the sheet: who, where, the steps newest first with Now, Take control, and no screen", async () => {
    show(true);
    await userEvent.click(screen.getByRole("button", { name: /Chief’s computer/ }));
    const sheet = await screen.findByRole("dialog", { name: "Chief’s computer" });
    const steps = within(sheet).getAllByRole("listitem");
    expect(steps.map((li) => li.textContent)).toEqual([
      "Typed into 'Search' (5 characters)Now", "Clicked 'Item 2'16:05", "Looked at the screen16:05",
    ]);
    expect(sheet.querySelector(".cc-screen")).toBeNull();
    expect(screenState.opened).toBe(0);
    await userEvent.click(within(sheet).getByRole("button", { name: "Take control" }));
    expect(takeControl).toHaveBeenCalledWith("bot-1");
    expect(navigate).toHaveBeenCalledWith("/bots/bot-1?panel=computer");
  });

  it("the sheet's Open computer goes to the bot's Computer tab, where the screen lives", async () => {
    show(false);
    await userEvent.click(screen.getByRole("button", { name: /Used its computer/ }));
    const sheet = await screen.findByRole("dialog");
    await userEvent.click(within(sheet).getByRole("button", { name: "Open computer" }));
    expect(navigate).toHaveBeenCalledWith("/bots/bot-1?panel=computer");
    expect(takeControl).not.toHaveBeenCalled();
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("the folded line opens the same steps, with times and no Now", async () => {
    show(false);
    await userEvent.click(screen.getByRole("button", { name: /Used its computer/ }));
    const sheet = await screen.findByRole("dialog");
    expect(within(sheet).queryByText("Now")).toBeNull();
    expect(within(sheet).getAllByText("16:05")).toHaveLength(3);
  });

  it("a finished run is always the quiet line: no kept card, no screen", () => {
    show(false);
    expect(screen.queryByTestId("computer-kept")).toBeNull();
    expect(screen.queryByTestId("computer-card")).toBeNull();
    expect(screen.getByRole("button", { name: /Used its computer · www.upwork.com · 3 steps/ })).toBeInTheDocument();
    expect(screenState.opened).toBe(0);
  });
});
