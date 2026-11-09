import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { ComputerTab, SCREEN_REFRESH_MS } from "../src/components/profile/ComputerTab";
import { ApiError } from "../src/api/client";
import type { StuckCardOut } from "../src/api/types";
import { makeBot, makeStuckCard } from "./fixtures";

const computer = { fetchScreen: vi.fn(), getControl: vi.fn(), takeControl: vi.fn(), giveBack: vi.fn() };
const desk = { getDeskStatus: vi.fn(), startBrowser: vi.fn(), stopBrowser: vi.fn(), execWorkspace: vi.fn() };
vi.mock("../src/api/computer", () => ({
  fetchScreen: (id: string) => computer.fetchScreen(id), getControl: (id: string) => computer.getControl(id),
  takeControl: (id: string) => computer.takeControl(id), giveBack: (id: string) => computer.giveBack(id),
}));
const teach = { getTeach: vi.fn(), startTeach: vi.fn() };
vi.mock("../src/api/teach", () => ({
  getTeach: (id: string) => teach.getTeach(id), startTeach: (id: string) => teach.startTeach(id),
}));
const stuck = { listStuck: vi.fn(), clearStuck: vi.fn() };
vi.mock("../src/api/stuck", () => ({
  listStuck: () => stuck.listStuck(), clearStuck: (id: string) => stuck.clearStuck(id),
}));
// The live stuck_card frames this page has heard, set per test.
let liveCards: Record<string, StuckCardOut> = {};
// The bots as the live store last heard them, set per test (the tab reloads when its bot's status changes).
let liveBots: Record<string, ReturnType<typeof makeBot>> = {};
vi.mock("../src/hooks/useLiveStore", () => ({ useLiveState: () => ({ stuckCards: liveCards, bots: liveBots }) }));
vi.mock("../src/api/desk", () => ({
  getDeskStatus: (id: string) => desk.getDeskStatus(id), startBrowser: (id: string) => desk.startBrowser(id),
  stopBrowser: (id: string) => desk.stopBrowser(id), execWorkspace: (id: string, c: string) => desk.execWorkspace(id, c),
}));

vi.mock("../src/components/computer/ControlScreen", () => ({
  ControlScreen: ({ onClosed, teaching }: { onClosed: () => void; teaching?: boolean }) => (
    <div role="dialog" aria-label="control" data-teaching={String(Boolean(teaching))}>
      <button type="button" onClick={onClosed}>close control</button>
    </div>
  ),
}));
vi.mock("../src/components/computer/SiteLogins", () => ({ SiteLogins: () => <h2>Vault: site logins</h2> }));
vi.mock("../src/components/computer/AppsList", () => ({ AppsList: () => <h2>Apps</h2> }));
vi.mock("../src/components/computer/LiveScreen", () => ({
  LiveScreen: ({ bot }: { bot: { name: string } }) => <div aria-label={`${bot.name}’s screen, live`} />,
}));

const BOT = makeBot({ id: "bot-1", name: "Scout" });
const CARD = makeStuckCard({ thread_id: "t-2" });
const HELD = { held: true, since: "2026-10-14T10:00:00Z" };
const FREE = { held: false, since: null };
const renderTab = () => render(<MemoryRouter><ComputerTab bot={BOT} onChange={() => undefined} /></MemoryRouter>);

beforeEach(() => {
  URL.createObjectURL = vi.fn(() => "blob:screen");
  URL.revokeObjectURL = vi.fn();
  computer.getControl.mockResolvedValue(FREE);
  teach.getTeach.mockResolvedValue({ teaching: false, steps: 0, capped: false, started_at: null });
  computer.fetchScreen.mockResolvedValue({ kind: "asleep" });
  desk.getDeskStatus.mockResolvedValue({ browser: "stopped", workspace: "absent" });
  stuck.listStuck.mockResolvedValue([]);
  stuck.clearStuck.mockResolvedValue({ ...CARD, state: "cleared", closed_at: "2026-10-14T10:05:00Z" });
  liveCards = {};
  liveBots = {};
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  [...Object.values(computer), ...Object.values(desk), ...Object.values(stuck), ...Object.values(teach)]
    .forEach((m) => m.mockReset());
});

describe("ComputerTab on a Linux computer", () => {
  const LINUX = makeBot({ id: "bot-1", name: "Scout", computer: "linux" });
  const renderLinux = () => render(<MemoryRouter><ComputerTab bot={LINUX} onChange={() => undefined} /></MemoryRouter>);

  it("a Linux bot shows the live screen when running and Computer is asleep otherwise", async () => {
    desk.getDeskStatus.mockResolvedValue({ browser: "running", workspace: "absent", computer: "linux" });
    renderLinux();
    expect(await screen.findByLabelText("Scout’s screen, live")).toBeInTheDocument();
    expect(computer.fetchScreen).not.toHaveBeenCalled();
    cleanup();
    desk.getDeskStatus.mockResolvedValue({ browser: "stopped", workspace: "absent", computer: "linux" });
    desk.startBrowser.mockResolvedValue({ browser: "running", workspace: "absent", computer: "linux" });
    renderLinux();
    expect(await screen.findByRole("heading", { name: "Computer is asleep" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Open it" }));
    expect(desk.startBrowser).toHaveBeenCalledWith("bot-1");
    expect(await screen.findByLabelText("Scout’s screen, live")).toBeInTheDocument();
  });

  it("looks again when the bot's status changes, so a computer the bot woke shows live", async () => {
    desk.getDeskStatus.mockResolvedValue({ browser: "stopped", workspace: "absent", computer: "linux" });
    liveBots = { [LINUX.id]: { ...LINUX, status: "on_it" } };
    const view = renderLinux();
    expect(await screen.findByText(/Computer is asleep/)).toBeInTheDocument();
    desk.getDeskStatus.mockResolvedValue({ browser: "running", workspace: "absent", computer: "linux" });
    liveBots = { [LINUX.id]: { ...LINUX, status: "resting" } };
    view.rerender(<MemoryRouter><ComputerTab bot={LINUX} onChange={() => undefined} /></MemoryRouter>);
    expect(await screen.findByLabelText("Scout’s screen, live")).toBeInTheDocument();
    expect(desk.getDeskStatus).toHaveBeenCalledTimes(2);
  });

  it("Take control wakes a sleeping computer, takes control and opens the full screen", async () => {
    desk.getDeskStatus.mockResolvedValue({ browser: "stopped", workspace: "absent", computer: "linux" });
    desk.startBrowser.mockResolvedValue({ browser: "running", workspace: "absent", computer: "linux" });
    computer.takeControl.mockResolvedValue(HELD);
    renderLinux();
    await userEvent.click(await screen.findByRole("button", { name: "Take control" }));
    expect(desk.startBrowser).toHaveBeenCalledWith("bot-1");
    expect(computer.takeControl).toHaveBeenCalledWith("bot-1");
    expect(await screen.findByRole("dialog", { name: "control" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "close control" }));
    expect(screen.queryByRole("dialog", { name: "control" })).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Vault: site logins" })).toBeInTheDocument();
  });

  it("Teach starts teaching, takes control and opens the full screen in teach mode", async () => {
    desk.getDeskStatus.mockResolvedValue({ browser: "running", workspace: "absent", computer: "linux" });
    teach.startTeach.mockResolvedValue({ teaching: true, steps: 0, capped: false, started_at: "2026-10-22T10:00:00Z" });
    renderLinux();
    await userEvent.click(await screen.findByRole("button", { name: "Teach" }));
    expect(teach.startTeach).toHaveBeenCalledWith("bot-1");
    expect(computer.takeControl).not.toHaveBeenCalled();
    expect(await screen.findByRole("dialog", { name: "control" })).toHaveAttribute("data-teaching", "true");
    await userEvent.click(screen.getByRole("button", { name: "close control" }));
    expect(screen.queryByRole("dialog", { name: "control" })).not.toBeInTheDocument();
  });

  it("a bot still being taught opens in teach mode, and a refused Teach says why", async () => {
    computer.getControl.mockResolvedValue(HELD);
    teach.getTeach.mockResolvedValue({ teaching: true, steps: 2, capped: false, started_at: "2026-10-22T10:00:00Z" });
    desk.getDeskStatus.mockResolvedValue({ browser: "running", workspace: "absent", computer: "linux" });
    renderLinux();
    await waitForTeaching();
    cleanup();
    computer.getControl.mockResolvedValue(FREE);
    teach.getTeach.mockResolvedValue({ teaching: false, steps: 0, capped: false, started_at: null });
    teach.startTeach.mockRejectedValue(new ApiError(409, "Teach works on the bot's Linux computer."));
    renderLinux();
    await userEvent.click(await screen.findByRole("button", { name: "Teach" }));
    expect(await screen.findByText(/Teach works on the bot's Linux computer/)).toBeInTheDocument();
  });

  it("a computer already held opens the full screen at once", async () => {
    computer.getControl.mockResolvedValue(HELD);
    desk.getDeskStatus.mockResolvedValue({ browser: "running", workspace: "absent", computer: "linux" });
    renderLinux();
    expect(await screen.findByRole("dialog", { name: "control" })).toBeInTheDocument();
  });

  it("on a phone, Take control is offered with no Mac-only note (the server decides who may)", async () => {
    const original = window.matchMedia;
    window.matchMedia = ((query: string) => ({
      matches: true, media: query, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
    })) as unknown as typeof window.matchMedia;
    desk.getDeskStatus.mockResolvedValue({ browser: "running", workspace: "absent", computer: "linux" });
    renderLinux();
    expect(await screen.findByRole("button", { name: "Take control" })).toBeInTheDocument();
    expect(screen.queryByText(/this Mac only/)).not.toBeInTheDocument();
    window.matchMedia = original;
  });

  it("the Linux computer | Mac Brave switch moved to Settings (restructure slice 3)", async () => {
    renderTab();
    expect(await screen.findByText(/screen/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Linux computer" })).not.toBeInTheDocument();
  });

  it("a Mac Brave bot keeps the old Take control", async () => {
    computer.fetchScreen.mockResolvedValue({ kind: "asleep" });
    computer.takeControl.mockResolvedValue(HELD);
    renderTab();
    await userEvent.click(await screen.findByRole("button", { name: "Take control" }));
    expect(await screen.findByText(/You have control/)).toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: "control" })).not.toBeInTheDocument();
    expect(desk.startBrowser).not.toHaveBeenCalled();
  });

  it("a Mac Brave bot keeps the screenshot", async () => {
    computer.fetchScreen.mockResolvedValue({ kind: "image", blob: new Blob(["x"]) });
    renderTab();
    expect(await screen.findByRole("img", { name: "Scout’s screen" })).toHaveAttribute("src", "blob:screen");
    expect(screen.queryByLabelText("Scout’s screen, live")).not.toBeInTheDocument();
  });

  it("a Linux bot never shows the Mac Brave Window box; a Mac Brave bot does", async () => {
    desk.getDeskStatus.mockResolvedValue({ browser: "running", workspace: "absent", computer: "linux" });
    renderLinux();
    await screen.findByLabelText("Scout’s screen, live");
    expect(screen.queryByRole("heading", { name: "Window" })).not.toBeInTheDocument();
    expect(screen.queryByText(/own Brave window on your Mac, kept apart/)).not.toBeInTheDocument();
    cleanup();
    renderTab();
    expect(await screen.findByRole("heading", { name: "Window" })).toBeInTheDocument();
  });

  it("says when all computers are busy", async () => {
    desk.getDeskStatus.mockResolvedValue({ browser: "stopped", workspace: "absent", computer: "linux" });
    desk.startBrowser.mockRejectedValue(new ApiError(409, "All computers are busy right now. Try again in a few minutes."));
    renderLinux();
    await userEvent.click(await screen.findByRole("button", { name: "Open it" }));
    expect(await screen.findByText("All computers are busy right now. Try again in a few minutes.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });
});

describe("ComputerTab", () => {
  it("a sleeping computer says so; Open it starts the browser, then the screen shows", async () => {
    computer.fetchScreen.mockResolvedValueOnce({ kind: "asleep" }).mockResolvedValue({ kind: "image", blob: new Blob(["x"]) });
    desk.startBrowser.mockResolvedValue({ browser: "running", workspace: "absent" });
    renderTab();
    expect(await screen.findByRole("heading", { name: "Computer is asleep" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Open it" }));
    expect(desk.startBrowser).toHaveBeenCalledWith("bot-1");
    expect(await screen.findByRole("img", { name: "Scout’s screen" })).toHaveAttribute("src", "blob:screen");
  });

  it("refreshes about every 3 seconds only while the page is visible", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    computer.fetchScreen.mockResolvedValue({ kind: "image", blob: new Blob(["x"]) });
    renderTab();
    await act(async () => { await vi.advanceTimersByTimeAsync(SCREEN_REFRESH_MS); });
    const calls = computer.fetchScreen.mock.calls.length;
    Object.defineProperty(document, "visibilityState", { value: "hidden", configurable: true });
    await act(async () => { await vi.advanceTimersByTimeAsync(SCREEN_REFRESH_MS * 3); });
    expect(computer.fetchScreen.mock.calls.length).toBe(calls);
    Object.defineProperty(document, "visibilityState", { value: "visible", configurable: true });
  });

  it("an unreachable screen offers Retry", async () => {
    computer.fetchScreen.mockResolvedValue({ kind: "unreachable" });
    renderTab();
    expect(await screen.findByText(/Can’t reach Scout’s screen/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("Take control, then Give it back", async () => {
    computer.fetchScreen.mockResolvedValue({ kind: "asleep" });
    computer.takeControl.mockResolvedValue({ held: true, since: "2026-10-14T10:00:00Z" });
    computer.giveBack.mockResolvedValue({ held: false, since: null });
    renderTab();
    await userEvent.click(await screen.findByRole("button", { name: "Take control" }));
    expect(computer.takeControl).toHaveBeenCalledWith("bot-1");
    expect(await screen.findByText(/You have control/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Give it back" }));
    expect(computer.giveBack).toHaveBeenCalledWith("bot-1");
    expect(screen.getByRole("heading", { name: "About this computer" })).toBeInTheDocument();
  });

  it("while the bot is stuck, Give it back clears its Stuck card so it carries on", async () => {
    stuck.listStuck.mockResolvedValue([CARD, makeStuckCard({ id: "card-2", bot_id: "bot-2" })]);
    computer.getControl.mockResolvedValue(HELD);
    renderTab();
    expect(await screen.findByText(/When you give it back, Scout carries on with the task it was stuck on/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "See the Stuck card" })).toHaveAttribute("href", "/bots/bot-1?thread=t-2");
    await userEvent.click(screen.getByRole("button", { name: "Give it back" }));
    expect(stuck.clearStuck).toHaveBeenCalledWith("card-1");
    expect(computer.giveBack).not.toHaveBeenCalled();
    expect(await screen.findByRole("button", { name: "Take control" })).toBeInTheDocument();
  });

  it("a card heard about live counts too", async () => {
    liveCards = { [CARD.id]: CARD };
    computer.getControl.mockResolvedValue(HELD);
    renderTab();
    await userEvent.click(await screen.findByRole("button", { name: "Give it back" }));
    expect(stuck.clearStuck).toHaveBeenCalledWith("card-1");
  });

  it("a card closed meanwhile: Give it back still hands the computer back", async () => {
    stuck.listStuck.mockResolvedValue([CARD]);
    stuck.clearStuck.mockRejectedValue(new ApiError(409, "This card is already closed."));
    computer.getControl.mockResolvedValue(HELD);
    computer.giveBack.mockResolvedValue(FREE);
    renderTab();
    await screen.findByText(/carries on with the task it was stuck on/);
    await userEvent.click(screen.getByRole("button", { name: "Give it back" }));
    expect(computer.giveBack).toHaveBeenCalledWith("bot-1");
    expect(await screen.findByRole("button", { name: "Take control" })).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("a failed clear says why and keeps the computer yours", async () => {
    stuck.listStuck.mockResolvedValue([CARD]);
    stuck.clearStuck.mockRejectedValue(new ApiError(500, "Something broke."));
    computer.getControl.mockResolvedValue(HELD);
    renderTab();
    await screen.findByText(/carries on with the task it was stuck on/);
    await userEvent.click(screen.getByRole("button", { name: "Give it back" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Something broke.");
    expect(computer.giveBack).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Give it back" })).toBeInTheDocument();
  });

  it("a closed card or another bot's card leaves Give it back as it is", async () => {
    liveCards = { [CARD.id]: { ...CARD, state: "given_up" } };
    stuck.listStuck.mockResolvedValue([CARD, makeStuckCard({ id: "card-2", bot_id: "bot-2" })]);
    computer.getControl.mockResolvedValue(HELD);
    computer.giveBack.mockResolvedValue(FREE);
    renderTab();
    await userEvent.click(await screen.findByRole("button", { name: "Give it back" }));
    expect(computer.giveBack).toHaveBeenCalledWith("bot-1");
    expect(stuck.clearStuck).not.toHaveBeenCalled();
    expect(screen.queryByText(/carries on with the task/)).not.toBeInTheDocument();
  });

  it("a failed card list says why, and the tab still works", async () => {
    stuck.listStuck.mockRejectedValue(new ApiError(500, "Could not load your Stuck cards."));
    renderTab();
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not load your Stuck cards.");
    expect(screen.getByRole("button", { name: "Take control" })).toBeInTheDocument();
  });
});

describe("About this computer", () => {
  it("a Linux bot's card names its Linux computer, the live screen and Take control, with no sealed box", async () => {
    render(<MemoryRouter><ComputerTab bot={makeBot({ id: "bot-1", name: "Scout", computer: "linux" })} onChange={() => undefined} /></MemoryRouter>);
    const card = (await screen.findByRole("heading", { name: "About this computer" })).closest("section")!;
    expect(card).toHaveTextContent(/own Linux computer with a browser and a live screen/);
    expect(card).toHaveTextContent(/Take control/);
    expect(card).toHaveTextContent(/Other bots can’t see its pages or logins/);
    expect(document.body.textContent ?? "").not.toMatch(/sealed box/i);
  });

  it("a Mac Brave bot keeps a short one-line note", async () => {
    renderTab();
    const card = (await screen.findByRole("heading", { name: "About this computer" })).closest("section")!;
    expect(card).toHaveTextContent("Scout works in its own Brave window on your Mac. Other bots can’t see its pages or logins.");
    expect(document.body.textContent ?? "").not.toMatch(/sealed box/i);
  });
});

async function waitForTeaching() {
  const dialog = await screen.findByRole("dialog", { name: "control" });
  await vi.waitFor(() => expect(dialog).toHaveAttribute("data-teaching", "true"));
}
