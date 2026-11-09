import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { BotMenu } from "../src/components/BotMenu";
import { makeBot } from "./fixtures";

const api = { stopBot: vi.fn(), setOffDuty: vi.fn(), starBot: vi.fn(), deleteBot: vi.fn(), setPinned: vi.fn() };
vi.mock("../src/api/bots", () => ({
  stopBot: (id: string) => api.stopBot(id), setOffDuty: (id: string, v: boolean) => api.setOffDuty(id, v),
  starBot: (id: string) => api.starBot(id), deleteBot: (id: string) => api.deleteBot(id), setPinned: (id: string, v: boolean) => api.setPinned(id, v),
}));

function renderMenu(bot = makeBot({ id: "bot-1", name: "Scout" }), onChange = vi.fn()) {
  render(
    <MemoryRouter initialEntries={["/bots/bot-1"]}>
      <Routes>
        <Route path="/" element={<p>Home</p>} />
        <Route path="/bots/:botId" element={<BotMenu bot={bot} onChange={onChange} onError={vi.fn()} />} />
      </Routes>
    </MemoryRouter>,
  );
  return onChange;
}

afterEach(() => { cleanup(); vi.restoreAllMocks(); Object.values(api).forEach((m) => m.mockReset()); });

describe("BotMenu", () => {
  it("offers Stop only while the bot is on it", async () => {
    renderMenu();
    await userEvent.click(screen.getByRole("button", { name: "Scout menu" }));
    expect(screen.getByRole("menuitem", { name: "Stop" })).toHaveAttribute("aria-disabled", "true");
  });

  it("offers Earlier conversations only where it is given (the chat header), not on the profile", async () => {
    const onEarlier = vi.fn();
    const first = render(<MemoryRouter><BotMenu bot={makeBot({ name: "Scout" })} onChange={vi.fn()} onError={vi.fn()} onEarlier={onEarlier} /></MemoryRouter>);
    await userEvent.click(screen.getByRole("button", { name: "Scout menu" }));
    await userEvent.click(screen.getByRole("menuitem", { name: "Earlier conversations" }));
    expect(onEarlier).toHaveBeenCalledTimes(1);
    first.unmount();
    renderMenu();
    await userEvent.click(screen.getByRole("button", { name: "Scout menu" }));
    expect(screen.queryByRole("menuitem", { name: "Earlier conversations" })).not.toBeInTheDocument();
  });

  it("offers Fresh start on the chat header", async () => {
    const onFreshStart = vi.fn();
    render(<MemoryRouter><BotMenu bot={makeBot({ name: "Scout" })} onChange={vi.fn()} onError={vi.fn()}
      onFreshStart={onFreshStart} /></MemoryRouter>);
    await userEvent.click(screen.getByRole("button", { name: "Scout menu" }));
    await userEvent.click(screen.getByRole("menuitem", { name: "Fresh start" }));
    expect(onFreshStart).toHaveBeenCalledTimes(1);
  });

  it("has no New conversation: a bot has one chat", async () => {
    renderMenu();
    await userEvent.click(screen.getByRole("button", { name: "Scout menu" }));
    expect(screen.queryByRole("menuitem", { name: "New conversation" })).not.toBeInTheDocument();
    expect(screen.getAllByRole("menuitem").length).toBeGreaterThan(0);
  });

  it("Off duty and Make main bot update the bot", async () => {
    const offDuty = makeBot({ id: "bot-1", name: "Scout", off_duty: true });
    api.setOffDuty.mockResolvedValue(offDuty);
    const onChange = renderMenu();
    await userEvent.click(screen.getByRole("button", { name: "Scout menu" }));
    await userEvent.click(screen.getByRole("menuitem", { name: "Off duty" }));
    expect(api.setOffDuty).toHaveBeenCalledWith("bot-1", true);
    await vi.waitFor(() => expect(onChange).toHaveBeenCalledWith(offDuty));
    expect(screen.queryByRole("menuitem")).not.toBeInTheDocument();
  });

  it("the main bot cannot be retired from its menu and has no Make main bot", async () => {
    renderMenu(makeBot({ id: "bot-1", name: "Chief", is_primary: true }));
    await userEvent.click(screen.getByRole("button", { name: "Chief menu" }));
    expect(screen.queryByRole("menuitem", { name: "Make main bot" })).not.toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Retire this bot" })).toHaveAttribute("aria-disabled", "true");
  });

  it("Retire this bot asks first, then deletes and goes Home", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    api.deleteBot.mockResolvedValue(undefined);
    renderMenu();
    await userEvent.click(screen.getByRole("button", { name: "Scout menu" }));
    await userEvent.click(screen.getByRole("menuitem", { name: "Retire this bot" }));
    expect(api.deleteBot).toHaveBeenCalledWith("bot-1");
    expect(await screen.findByText("Home")).toBeInTheDocument();
  });

  it("Pin puts the bot in the robot row, and Unpin takes it out", async () => {
    const pinned = makeBot({ id: "bot-1", name: "Scout", pinned: true, pinned_at: "x" });
    api.setPinned.mockResolvedValue(pinned);
    const onChange = renderMenu();
    await userEvent.click(screen.getByRole("button", { name: "Scout menu" }));
    await userEvent.click(screen.getByRole("menuitem", { name: "Pin" }));
    expect(api.setPinned).toHaveBeenCalledWith("bot-1", true);
    await vi.waitFor(() => expect(onChange).toHaveBeenCalledWith(pinned));
    cleanup();
    api.setPinned.mockResolvedValue(makeBot({ id: "bot-1", name: "Scout" }));
    renderMenu(pinned);
    await userEvent.click(screen.getByRole("button", { name: "Scout menu" }));
    await userEvent.click(screen.getByRole("menuitem", { name: "Unpin" }));
    expect(api.setPinned).toHaveBeenLastCalledWith("bot-1", false);
  });

  it("on the chat it opens with View profile, Find in chat and Share as Template, and ends with Retire this bot", async () => {
    const calls = { profile: vi.fn(), find: vi.fn(), share: vi.fn() };
    render(<MemoryRouter><BotMenu bot={makeBot({ name: "Scout" })} onChange={vi.fn()} onError={vi.fn()}
      onProfile={calls.profile} onFind={calls.find} onShare={calls.share} onEarlier={vi.fn()} /></MemoryRouter>);
    await userEvent.click(screen.getByRole("button", { name: "Scout menu" }));
    const names = screen.getAllByRole("menuitem").map((item) => item.textContent);
    expect(names.slice(0, 3)).toEqual(["View profile", "Find in chat", "Share as Template"]);
    expect(names[names.length - 1]).toBe("Retire this bot");
    expect(screen.getByRole("menuitem", { name: "Retire this bot" })).toHaveClass("menu__item--danger");
    for (const [name, call] of [["View profile", calls.profile], ["Find in chat", calls.find], ["Share as Template", calls.share]] as const) {
      await userEvent.click(screen.getByRole("menuitem", { name }));
      expect(call).toHaveBeenCalledTimes(1);
      await userEvent.click(screen.getByRole("button", { name: "Scout menu" }));
    }
  });

  it("Retire this bot does nothing when the confirm is declined", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(false);
    renderMenu();
    await userEvent.click(screen.getByRole("button", { name: "Scout menu" }));
    await userEvent.click(screen.getByRole("menuitem", { name: "Retire this bot" }));
    expect(api.deleteBot).not.toHaveBeenCalled();
  });

  it("the main bot is always pinned, so its menu has no Pin", async () => {
    renderMenu(makeBot({ id: "bot-1", name: "Chief", is_primary: true }));
    await userEvent.click(screen.getByRole("button", { name: "Chief menu" }));
    expect(screen.queryByRole("menuitem", { name: /pin/i })).not.toBeInTheDocument();
  });
});
