import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ComputerPanel } from "../ComputerPanel";
import { ComputerAsleep } from "./ComputerAsleep";
import { ErrorNotice } from "../ErrorNotice";
import * as computerApi from "../../api/computer";
import type { ScreenResult } from "../../api/computer";
import * as deskApi from "../../api/desk";
import * as stuckApi from "../../api/stuck";
import { ApiError, describeError } from "../../api/client";
import type { BotOut, ControlOut, DeskStatusOut, StuckCardOut } from "../../api/types";
import { useLiveState } from "../../hooks/useLiveStore";
import { LiveScreen } from "../computer/LiveScreen";
import { LinuxControl } from "../computer/LinuxControl";
import { SiteLogins } from "../computer/SiteLogins";
import { AppsList } from "../computer/AppsList";
import { WorkspaceFiles } from "../computer/WorkspaceFiles";
import { WorkspaceInternetSwitch } from "../computer/WorkspaceInternetSwitch";
import { COMPUTERS_BUSY_TEXT } from "../computer/constants";
import { mergeStuck, openStuckCards } from "../../lib/stuck";

export const SCREEN_REFRESH_MS = 3000;
type Screen = { kind: "loading" } | { kind: "asleep" } | { kind: "unreachable" } | { kind: "image"; url: string };

// The latest screenshot, refreshed about every 3 s while the page is visible (S1.8).
// One request at a time: a slow computer never piles screenshots up.
function useScreen(botId: string, enabled: boolean) {
  const [screen, setScreen] = useState<Screen>({ kind: "loading" });
  const [tick, setTick] = useState(0);
  const current = useRef<string | null>(null);
  useEffect(() => {
    let cancelled = false;
    let busy = false;
    if (!enabled) return;
    const load = async () => {
      if (busy || document.visibilityState !== "visible") return;
      busy = true;
      const result = await computerApi.fetchScreen(botId).catch((): ScreenResult => ({ kind: "unreachable" }));
      busy = false;
      if (cancelled) return;
      if (result.kind !== "image") return setScreen(result);
      const previous = current.current;
      current.current = URL.createObjectURL(result.blob);
      setScreen({ kind: "image", url: current.current });
      if (previous) URL.revokeObjectURL(previous);
    };
    void load();
    const timer = setInterval(() => void load(), SCREEN_REFRESH_MS);
    return () => { cancelled = true; clearInterval(timer); };
  }, [botId, tick, enabled]);
  useEffect(() => () => { if (current.current) URL.revokeObjectURL(current.current); }, []);
  return { screen, refresh: useCallback(() => setTick((value) => value + 1), []) };
}

interface ScreenBoxProps { bot: BotOut; screen: Screen; onOpen: () => void; onRetry: () => void }

function ScreenBox({ bot, screen, onOpen, onRetry }: ScreenBoxProps) {
  if (screen.kind === "image") return <img className="screen-box__image" src={screen.url} alt={`${bot.name}’s screen`} />;
  if (screen.kind === "asleep") {
    return <ComputerAsleep bot={bot} onOpen={onOpen} />;
  }
  if (screen.kind === "unreachable") {
    return <p className="screen-box__state">Can&rsquo;t reach {bot.name}&rsquo;s screen · <button type="button" className="link-btn" onClick={onRetry}>Retry</button></p>;
  }
  return <p className="screen-box__state">Looking at {bot.name}&rsquo;s screen&hellip;</p>;
}

// A clear that answers 404 or 409 found the card already closed (another tab, Give up in the chat).
const CARD_GONE_STATUSES: ReadonlySet<number> = new Set([404, 409]);

// The bot's open Stuck card, if any: GET /api/stuck once, kept current by live stuck_card frames.
// A failed load is said; Give it back then only hands the computer back.
function useOpenStuckCard(botId: string) {
  const live = useLiveState();
  const [loaded, setLoaded] = useState<StuckCardOut[]>([]);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let cancelled = false;
    stuckApi.listStuck()
      .then((cards) => { if (!cancelled) setLoaded(cards); })
      .catch((err: unknown) => { if (!cancelled) setError(describeError(err)); });
    return () => { cancelled = true; };
  }, [botId]);
  const card = openStuckCards(mergeStuck(loaded, live.stuckCards)).find((open) => open.bot_id === botId);
  return { card, error };
}

// Give it back. While the bot has an open Stuck card it does what the card's own Give it back
// does: the card is cleared, which also hands the computer back, and the bot carries on.
async function giveBackFor(botId: string, card: StuckCardOut | undefined): Promise<ControlOut> {
  if (!card) return computerApi.giveBack(botId);
  try {
    await stuckApi.clearStuck(card.id);
    return { held: false, since: null };
  } catch (err) {
    if (err instanceof ApiError && CARD_GONE_STATUSES.has(err.status)) return computerApi.giveBack(botId);
    throw err;
  }
}

function ControlNote({ bot, card }: { bot: BotOut; card: StuckCardOut | undefined }) {
  return (
    <>
      <p className="control__note">You have control. {bot.name}&rsquo;s browser calls wait until you give it back. Work in
        {" "}{bot.name}&rsquo;s Brave window on your Mac; taking control from the phone comes later.</p>
      {card ? (
        <p className="control__note">When you give it back, {bot.name} carries on with the task it was stuck on.{" "}
          <Link to={`/bots/${bot.id}?thread=${encodeURIComponent(card.thread_id)}`}>See the Stuck card</Link></p>
      ) : null}
    </>
  );
}

function ControlButton({ bot, card }: { bot: BotOut; card: StuckCardOut | undefined }) {
  const [held, setHeld] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    computerApi.getControl(bot.id).then((c) => setHeld(c.held)).catch((err: unknown) => setError(describeError(err)));
  }, [bot.id]);
  const toggle = async () => {
    setError(null);
    try {
      setHeld((await (held ? giveBackFor(bot.id, card) : computerApi.takeControl(bot.id))).held);
    } catch (err) {
      setError(describeError(err));
    }
  };
  return (
    <div className="control">
      <button type="button" className={`btn ${held ? "btn--danger" : "btn--primary"}`} onClick={() => void toggle()}>
        {held ? "Give it back" : "Take control"}
      </button>
      {held ? <ControlNote bot={bot} card={card} /> : null}
      {error ? <ErrorNotice message={error} /> : null}
    </div>
  );
}

// Open or close the bot's window, then look again; a failure is said, never swallowed. A new reloadKey (the bot's
// status) looks again too, so a computer the bot woke on its own shows live.
function useWindowActions(botId: string, refresh: () => void, reloadKey: string | undefined) {
  const [status, setStatus] = useState<DeskStatusOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { deskApi.getDeskStatus(botId).then(setStatus).catch(() => setStatus(null)); }, [botId, reloadKey]);
  const run = useCallback(async (action: (id: string) => Promise<DeskStatusOut>) => {
    setError(null);
    try {
      setStatus(await action(botId));
    } catch (err) {
      setError(describeError(err));
    }
    refresh();
  }, [botId, refresh]);
  const asleep = useCallback(() => setStatus((current) => (current ? { ...current, browser: "stopped" } : current)), []);
  return { status, error, asleep, open: () => run(deskApi.startBrowser), close: () => run(deskApi.stopBrowser) };
}

interface LinuxScreenProps { bot: BotOut; status: DeskStatusOut | null; busy: boolean; onOpen: () => void; onAsleep: () => void }

// A Linux bot's screen box: live when its computer runs, Computer is asleep otherwise (C1).
function LinuxScreen({ bot, status, busy, onOpen, onAsleep }: LinuxScreenProps) {
  if (busy) {
    return <p className="screen-box__state">{COMPUTERS_BUSY_TEXT}{" "}<button type="button" className="link-btn" onClick={onOpen}>Retry</button></p>;
  }
  if (!status) return <p className="screen-box__state">Looking at {bot.name}&rsquo;s screen&hellip;</p>;
  if (status.browser === "running") return <LiveScreen bot={bot} mode="view" onAsleep={onAsleep} />;
  return <ComputerAsleep bot={bot} onOpen={onOpen} />;
}

function AboutComputer({ bot }: { bot: BotOut }) {
  return (
    <section className="about-computer" aria-labelledby="about-computer-title">
      <h2 id="about-computer-title" className="about-computer__title">About this computer</h2>
      {bot.computer === "linux" ? (
        <p>{bot.name} has its own Linux computer with a browser and a live screen, and you can Take control of it
          whenever you like. Other bots can&rsquo;t see its pages or logins.</p>
      ) : (
        <p>{bot.name} works in its own Brave window on your Mac. Other bots can&rsquo;t see its pages or logins.</p>
      )}
    </section>
  );
}

export function ComputerTab({ bot, onChange }: { bot: BotOut; onChange: (bot: BotOut) => void }) {
  const linux = bot.computer === "linux";
  const { screen, refresh } = useScreen(bot.id, !linux);
  const botStatus = useLiveState().bots?.[bot.id]?.status;
  const { status, error, asleep, open, close } = useWindowActions(bot.id, refresh, botStatus);
  const stuck = useOpenStuckCard(bot.id);
  const [loginsKey, setLoginsKey] = useState(0);
  const busy = linux && error === COMPUTERS_BUSY_TEXT;
  const controlClosed = () => { setLoginsKey((key) => key + 1); refresh(); };
  return (
    <div className="computer-tab">
      <figure className="computer-tab__screen">
        <div className="screen-box">
          {linux
            ? <LinuxScreen bot={bot} status={status} busy={busy} onOpen={() => void open()} onAsleep={asleep} />
            : <ScreenBox bot={bot} screen={screen} onOpen={() => void open()} onRetry={refresh} />}
        </div>
        <figcaption className="computer-tab__caption">{bot.name}&rsquo;s screen</figcaption>
      </figure>
      {linux
        ? <LinuxControl bot={bot} card={stuck.card} running={status ? status.browser === "running" : null} wake={open} onClosed={controlClosed} />
        : <ControlButton bot={bot} card={stuck.card} />}
      {linux ? <SiteLogins botId={bot.id} reloadKey={loginsKey} /> : null}
      {linux ? <AppsList botId={bot.id} reloadKey={botStatus} /> : null}
      {stuck.error ? <ErrorNotice message={stuck.error} /> : null}
      {error && !busy ? <ErrorNotice message={error} /> : null}
      {linux ? null : <ComputerPanel status={status} onStartBrowser={open} onStopBrowser={close} />}
      <WorkspaceFiles botId={bot.id} botName={bot.name}>
        <WorkspaceInternetSwitch bot={bot} onChange={onChange} />
      </WorkspaceFiles>
      <AboutComputer bot={bot} />
    </div>
  );
}
