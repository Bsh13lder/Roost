// The Sign-in card (docs/plans/2026-10-22-roost-signin.md): a Linux bot's sign-in Stuck card with
// Take control · Later (Check again a quiet text button), and "Keep me signed in on this computer?" on I'm done.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { StuckCard } from "../src/components/StuckCard";
import { GiveBackForm } from "../src/components/computer/GiveBackForm";
import { SiteLogins } from "../src/components/computer/SiteLogins";
import { parseStuckMessage } from "../src/lib/stuck";
import type { StuckMessageData } from "../src/api/types";
import { ToastProvider } from "../src/ui/Toast";
import { makeBot, makeStuckCard, stuckBody } from "./fixtures";

const computer = { getControl: vi.fn(), takeControl: vi.fn() };
const stuck = { clearStuck: vi.fn(), giveUpStuck: vi.fn(), openInMainBrowser: vi.fn(), openSignIn: vi.fn(), laterStuck: vi.fn() };
const vault = { listSiteLogins: vi.fn(), forgetSiteLogin: vi.fn(), signOutSiteLogin: vi.fn() };
vi.mock("../src/api/computer", () => ({
  getControl: (id: string) => computer.getControl(id),
  takeControl: (id: string) => computer.takeControl(id),
}));
vi.mock("../src/api/stuck", () => ({
  clearStuck: (...a: unknown[]) => stuck.clearStuck(...a),
  giveUpStuck: (id: string) => stuck.giveUpStuck(id),
  openInMainBrowser: (id: string) => stuck.openInMainBrowser(id),
  openSignIn: (id: string) => stuck.openSignIn(id),
  laterStuck: (id: string) => stuck.laterStuck(id),
}));
vi.mock("../src/api/vault", () => ({
  listSiteLogins: (id: string) => vault.listSiteLogins(id),
  forgetSiteLogin: (id: string, loginId: string) => vault.forgetSiteLogin(id, loginId),
  signOutSiteLogin: (id: string, loginId: string) => vault.signOutSiteLogin(id, loginId),
}));

// The live screen stands in as a labelled box that says its mode: noVNC and the socket are LiveScreen's own tests.
vi.mock("../src/components/computer/LiveScreen", () => ({
  LiveScreen: ({ bot, mode }: { bot: { name: string }; mode: string }) => (
    <div role="img" aria-label={`${bot.name}’s screen, live`} data-mode={mode} />
  ),
}));

const CARD = makeStuckCard({ sign_in: true });
const LINE = "shop.example's sign-in page is open on my computer. Take control, type your email and password, then press I'm done. Roost never sees your password.";
const DATA: StuckMessageData = {
  card_id: CARD.id, bot_id: CARD.bot_id, reason: "login", host: CARD.host, url: CARD.url, note: "",
  suggest_main_browser: false, line: LINE, sign_in: true,
};

function Where() {
  const location = useLocation();
  return <p data-testid="where">{`${location.pathname}${location.search}`}</p>;
}

const renderCard = (tainted = false) => render(
  <MemoryRouter initialEntries={["/bots/bot-1"]}>
    <Routes><Route path="*" element={<><StuckCard data={DATA} card={CARD} botName="Scout" tainted={tainted} /><Where /></>} /></Routes>
  </MemoryRouter>,
);
const click = (name: string) => userEvent.click(screen.getByRole("button", { name }));

beforeEach(() => {
  computer.getControl.mockResolvedValue({ held: false, since: null });
  stuck.openSignIn.mockResolvedValue(CARD);
  stuck.clearStuck.mockResolvedValue({ ...CARD, state: "cleared", closed_at: "2026-10-22T10:00:00Z" });
  stuck.laterStuck.mockResolvedValue({ ...CARD, state: "given_up", closed_at: "2026-10-22T10:00:00Z" });
});
afterEach(() => { cleanup(); [...Object.values(computer), ...Object.values(stuck), ...Object.values(vault)].forEach((m) => m.mockReset()); });

describe("Sign-in card", () => {
  it("reads sign_in from the message body, and an older body is not a sign-in", () => {
    expect(parseStuckMessage(stuckBody(CARD))?.sign_in).toBeFalsy();
    expect(parseStuckMessage(JSON.stringify({ ...DATA }))?.sign_in).toBe(true);
  });

  it("shows Take control and Later, with Check again as a quiet text button, and says Roost never sees your password", () => {
    renderCard();
    const card = screen.getByRole("group", { name: "Sign in on shop.example" });
    expect(card).toHaveTextContent(
      "shop.example's sign-in page is open on Scout's computer. Take control, type your email and password, then press I'm done.");
    expect(card).toHaveTextContent("Roost never sees your password.");
    for (const name of ["Take control", "Later", "Check again"]) expect(screen.getByRole("button", { name })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Check again" })).toHaveClass("btn--ghost");
    for (const name of ["Open sign-in", "Try again", "Use my main Brave", "Give up"]) {
      expect(screen.queryByRole("button", { name })).not.toBeInTheDocument();
    }
  });

  it("shows only the host, never the long address, and no web-page warning", () => {
    renderCard(true);
    const card = screen.getByRole("group", { name: "Sign in on shop.example" });
    expect(card).not.toHaveTextContent(CARD.url);
    expect(card).not.toHaveTextContent("This link came from a web page");
  });

  it("Take control asks the server to open the sign-in page and, with no bot at hand, opens its Computer tab", async () => {
    renderCard();
    await click("Take control");
    expect(stuck.openSignIn).toHaveBeenCalledWith("card-1");
    expect(computer.takeControl).not.toHaveBeenCalled();
    await waitFor(() => expect(screen.getByTestId("where")).toHaveTextContent("/bots/bot-1?panel=computer"));
  });

  it("Check again tries again, and Later leaves it for later", async () => {
    renderCard();
    await click("Check again");
    expect(stuck.clearStuck).toHaveBeenCalledWith("card-1", { how: "try_again" });
    cleanup();
    renderCard();
    await click("Later");
    expect(stuck.laterStuck).toHaveBeenCalledWith("card-1");
    expect(await screen.findByText("Stopped: shop.example")).toBeInTheDocument();
  });
});

describe("Keep me signed in on this computer?", () => {
  it("Give it back on a held Sign-in card asks the question before it clears the card", async () => {
    computer.getControl.mockResolvedValue({ held: true, since: "2026-10-22T10:00:00Z" });
    renderCard();
    await screen.findByRole("button", { name: "Give it back" });
    await click("Give it back");
    expect(stuck.clearStuck).not.toHaveBeenCalled();
    expect(screen.getByText("Keep me signed in on this computer?")).toBeInTheDocument();
    await click("No, this time");
    expect(stuck.clearStuck).toHaveBeenCalledWith("card-1", { keep: false });
    expect(await screen.findByText("Cleared: shop.example")).toBeInTheDocument();
  });

  it("Back from the question returns to the Holding view without clearing", async () => {
    computer.getControl.mockResolvedValue({ held: true, since: "2026-10-22T10:00:00Z" });
    renderCard();
    await screen.findByRole("button", { name: "Give it back" });
    await click("Give it back");
    await click("Back");
    expect(screen.getByRole("button", { name: "Give it back" })).toBeInTheDocument();
    expect(stuck.clearStuck).not.toHaveBeenCalled();
  });

  it("Yes keeps the login and No, this time does not", async () => {
    const onConfirm = vi.fn();
    render(<GiveBackForm host="shop.example" signIn busy={false} error={null} onConfirm={onConfirm} onBack={() => {}} />);
    expect(screen.getByText("Keep me signed in on this computer?")).toBeInTheDocument();
    expect(screen.getByText(/Roost never sees your password\./)).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText(/Which account did you use\?/), "me@shop");
    await click("Yes, keep me signed in");
    expect(onConfirm).toHaveBeenLastCalledWith("me@shop", true);
    await click("No, this time");
    expect(onConfirm).toHaveBeenLastCalledWith("me@shop", false);
    expect(screen.queryByRole("button", { name: "Give it back" })).not.toBeInTheDocument();
  });
});

describe("Sign in right in the chat", () => {
  const BOT = makeBot({ name: "Scout", computer: "linux" });
  const realMatchMedia = window.matchMedia;
  const phoneWidth = () => {
    window.matchMedia = ((query: string) => ({
      matches: true, media: query, addEventListener: () => {}, removeEventListener: () => {},
    })) as unknown as typeof window.matchMedia;
  };
  const renderWithBot = () => render(
    <ToastProvider>
      <MemoryRouter initialEntries={["/bots/bot-1"]}>
        <Routes><Route path="*" element={<><StuckCard data={DATA} card={CARD} botName="Scout" tainted={false} bot={BOT} /><Where /></>} /></Routes>
      </MemoryRouter>
    </ToastProvider>,
  );
  afterEach(() => { window.matchMedia = realMatchMedia; vi.unstubAllGlobals(); });

  it("shows a view-only preview while the card is on screen", async () => {
    vi.stubGlobal("IntersectionObserver", class {
      constructor(private readonly report: (entries: { isIntersecting: boolean }[]) => void) {}
      observe() { this.report([{ isIntersecting: true }]); }
      disconnect() {}
    });
    renderWithBot();
    expect(await screen.findByRole("img", { name: "Scout’s screen, live" })).toHaveAttribute("data-mode", "view");
  });

  it("Take control opens the screen in control under the card, with You're in control · I'm done · Full screen", async () => {
    renderWithBot();
    await click("Take control");
    expect(stuck.openSignIn).toHaveBeenCalledWith("card-1");
    const card = screen.getByRole("group", { name: "Sign in on shop.example" });
    expect(await within(card).findByRole("img", { name: "Scout’s screen, live" })).toHaveAttribute("data-mode", "control");
    expect(screen.getAllByRole("img", { name: "Scout’s screen, live" })).toHaveLength(1); // one socket, never two
    expect(card).toHaveTextContent("You're in control");
    expect(within(card).getByRole("button", { name: "Full screen" })).toBeInTheDocument();
    expect(screen.getByTestId("where")).toHaveTextContent("/bots/bot-1");
    expect(screen.getByTestId("where")).not.toHaveTextContent("panel=computer");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("I'm done still asks Keep me signed in on this computer?, then clears with keep", async () => {
    renderWithBot();
    await click("Take control");
    await click("I'm done");
    expect(stuck.clearStuck).not.toHaveBeenCalled();
    expect(screen.getByText("Keep me signed in on this computer?")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText(/Which account did you use\?/), "work email");
    await click("Yes, keep me signed in");
    expect(stuck.clearStuck).toHaveBeenCalledWith("card-1", { account: "work email", keep: true });
    expect(await screen.findByText("Cleared: shop.example")).toBeInTheDocument();
  });

  it("Full screen swaps the inline screen for the full-screen sheet", async () => {
    renderWithBot();
    await click("Take control");
    await click("Full screen");
    const sheet = await screen.findByRole("dialog");
    expect(within(sheet).getByRole("img", { name: "Scout’s screen, live" })).toHaveAttribute("data-mode", "control");
    expect(screen.getAllByRole("img", { name: "Scout’s screen, live" })).toHaveLength(1);
  });

  it("on a phone, Take control opens the full-screen sheet instead", async () => {
    phoneWidth();
    renderWithBot();
    await click("Take control");
    const sheet = await screen.findByRole("dialog");
    expect(within(sheet).getByText("You're in control")).toBeInTheDocument();
    // The sheet's screen is the only one: the card shows none beside it.
    expect(screen.getAllByLabelText("Scout’s screen, live")).toHaveLength(1);
    expect(within(sheet).getByLabelText("Scout’s screen, live")).toHaveAttribute("data-mode", "control");
  });
});

describe("Vault: Sign out", () => {
  it("shows whether a login is kept and signs out of one", async () => {
    vault.listSiteLogins.mockResolvedValue([
      { id: "l-1", bot_id: "bot-1", host: "shop.example", label: "me", updated_at: "2026-10-22T10:00:00Z", kept: true },
      { id: "l-2", bot_id: "bot-1", host: "bank.example", label: "", updated_at: "2026-10-22T10:00:00Z", kept: false },
    ]);
    vault.signOutSiteLogin.mockResolvedValue(undefined);
    render(<SiteLogins botId="bot-1" />);
    expect(await screen.findByText("shop.example · me")).toBeInTheDocument();
    expect(screen.getByText("bank.example · this time only")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Sign out of shop.example" }));
    expect(vault.signOutSiteLogin).toHaveBeenCalledWith("bot-1", "l-1");
    expect(screen.queryByText("shop.example · me")).not.toBeInTheDocument();
  });
});
