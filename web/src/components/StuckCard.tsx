// web/src/components/StuckCard.tsx — the Stuck card (stuck flow, Piece A). The bot hit a block
// it can't get past alone: a check that it's human, a sign-in page, a code check, a site that
// refused it, or something it asked you for. You clear it in the bot's own window (Take control,
// then Give it back), let it try again, open the page in your main Brave, or stop the task.
// A Sign-in card (a sign-in page on the bot's Linux computer) is calmer: it names only the host, says what to do,
// and has Take control (the server's open-sign-in: the card's page, then you hold control) · Later, with Check
// again as a quiet text button. Its Give it back first asks "Keep me signed in on this computer?" (the server
// refuses it without an answer). With the bot at hand (owner, 2026-10-22) the card shows its computer right in the
// chat (SignInLive): a small view-only preview while it waits, then after Take control the screen in control mode
// with You're in control · I'm done · Full screen. A phone, or Full screen, uses the full-screen sheet instead.
// Once the card is no longer open it folds to one line. Its quiet Reply (owner, 2026-11-02) quotes the card in the
// composer: whatever you then write (done, carry on, or a different task) answers it, and it folds to "You answered
// in the chat". Any message of yours in the card's chat answers it the same way.
import { useCallback, useEffect, useState, type ReactNode } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { ErrorNotice } from "./ErrorNotice";
import { GiveBackForm } from "./computer/GiveBackForm";
import { FoldCard, FoldedLine } from "./FoldCard";
import { SignInFullScreen, SignInInline, SignInPreview } from "./SignInLive";
import { SecretField, secretExplanation } from "./SecretField";
import * as computerApi from "../api/computer";
import * as stuckApi from "../api/stuck";
import { describeError } from "../api/client";
import type { BotOut, SecretFieldKind, StuckCardOut, StuckMessageData, StuckState } from "../api/types";
import { useMediaQuery } from "../hooks/useMediaQuery";
import { NEVER_SEES_PASSWORD, stuckTitle } from "../lib/stuck";
import { PHONE_QUERY } from "./panel/panelTabs";

export interface StuckCardProps {
  data: StuckMessageData;
  // The card's live state (GET /api/stuck merged with stuck_card frames). It is undefined when
  // this page has not heard of the card as open, e.g. an old card in a past conversation.
  card: StuckCardOut | undefined;
  botName: string;
  // The run that hit the block had read web content, so its address may be a planted one.
  tainted: boolean;
  // The card's bot, when the chat knows it: a Sign-in card then shows its computer right in the chat.
  bot?: BotOut;
  // Reply (owner, 2026-11-02): puts the card's quote in the composer; your message then answers the card (the
  // server closes it as "replied"). Left out where you can't write (a read-only chat).
  onReply?: () => void;
}

type View = "open" | "holding" | "main_opened";
// How a Sign-in card shows the computer: in the chat (desktop), in the full-screen sheet (a phone), or in the bot's
// Computer tab (no bot at hand, or that tab is already open beside the chat with its own live screen).
type LiveWhere = "inline" | "sheet" | "panel";
type CardAction = (cardId: string) => Promise<StuckCardOut>;

const TAINT_NOTE = "This link came from a web page the bot read. Check it before you open it.";
const FOLDED: Record<Exclude<StuckState, "open">, { word: string; icon: string }> = {
  cleared: { word: "Cleared", icon: "✓" },
  given_up: { word: "Stopped", icon: "×" },
  blocked: { word: "Blocked", icon: "!" },
  replied: { word: "You answered in the chat", icon: "↩" },
};

// The card as this page last heard of it. A closed live copy always wins, because a cleared card
// can still turn blocked. An open one gives way to what a button here just got back.
function latest(card: StuckCardOut | undefined, answered: StuckCardOut | null): StuckCardOut | undefined {
  if (!answered || (card && card.state !== "open")) return card;
  return answered;
}

// The buttons' calls: one at a time, and a failure is said on the card, never swallowed.
// An open card starts from who holds the bot's computer, so the Holding view (and its Give it
// back) survives a visit to the bot's screen. A "not held" answer never undoes a Take control.
function useStuckActions(cardId: string, botId: string, open: boolean) {
  const [answered, setAnswered] = useState<StuckCardOut | null>(null);
  const [holding, setHolding] = useState(false);
  const [full, setFull] = useState(false); // the full-screen sheet is open
  const [busy, setBusy] = useState(false);
  const [asking, setAsking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    computerApi.getControl(botId)
      .then((control) => { if (!cancelled && control.held) setHolding(true); })
      .catch((err: unknown) => { if (!cancelled) setError(describeError(err)); });
    return () => { cancelled = true; };
  }, [botId, open]);
  const run = async (action: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusy(false);
    }
  };
  const navigate = useNavigate();
  const answer = (call: CardAction) => run(async () => setAnswered(await call(cardId)));
  // Control ended under the inline screen or the sheet: a cleared card folds, anything else is no longer held.
  const closeControl = useCallback((cleared?: StuckCardOut) => {
    setFull(false);
    setAsking(false);
    if (cleared) setAnswered(cleared);
    else setHolding(false);
  }, []);
  return {
    answered, holding, busy, error, asking, full, closeControl,
    fullScreen: async () => { setAsking(false); setFull(true); },
    // A Sign-in card's Give it back: the question first, then the answer goes with the clear.
    ask: (on: boolean) => { setAsking(on); setError(null); },
    giveBack: (account: string | undefined, keep?: boolean) =>
      answer((id) => stuckApi.clearStuck(id, { ...(account ? { account } : {}), ...(keep !== undefined ? { keep } : {}) })),
    // The computer panel opens in control: its held state shows the full screen at once.
    takeControl: () => run(async () => {
      setHolding((await computerApi.takeControl(botId)).held);
      navigate(`/bots/${botId}?panel=computer`);
    }),
    clear: () => answer((id) => stuckApi.clearStuck(id)),
    giveUp: () => answer(stuckApi.giveUpStuck),
    openInMain: () => answer(stuckApi.openInMainBrowser),
    // The Sign-in card's Take control: the server shows the card's page on the bot's computer and hands you control.
    openSignIn: (where: LiveWhere) => run(async () => {
      await stuckApi.openSignIn(cardId);
      setHolding(true);
      if (where === "sheet") setFull(true);
      if (where === "panel") navigate(`/bots/${botId}?panel=computer`);
    }),
    checkAgain: () => answer((id) => stuckApi.clearStuck(id, { how: "try_again" })),
    // B3: the masked field's value goes straight to the server, which types it into the box; nothing keeps it.
    typeSecret: (value: string, save: boolean) => answer((id) => stuckApi.typeSecret(id, value, save)),
    later: () => answer(stuckApi.laterStuck),
  };
}

type Actions = ReturnType<typeof useStuckActions>;

function StuckFooter({ view, data, actions, signIn, live, field }: {
  view: View; data: StuckMessageData; actions: Actions; signIn: boolean; live: LiveWhere; field: boolean;
}) {
  const button = (label: string, onClick: () => Promise<void>, primary = false) => (
    <button type="button" className={`btn ${primary ? "btn--primary" : "btn--quiet"} btn--small`}
      disabled={actions.busy} onClick={() => void onClick()}>{label}</button>
  );
  if (view === "holding" && signIn && live !== "panel") {
    return (
      <>
        {live === "inline" ? <span className="sign-in-screen__state">You&apos;re in control</span> : null}
        {button(live === "inline" ? "I'm done" : "Give it back", async () => actions.ask(true), true)}
        {button("Full screen", actions.fullScreen)}
      </>
    );
  }
  if (view === "holding") {
    const giveBack = signIn ? async () => actions.ask(true) : actions.clear;
    return (
      <>
        <Link className="btn btn--quiet btn--small" to={`/bots/${data.bot_id}?panel=computer`}>See its screen</Link>
        {button("Give it back", giveBack, true)}
      </>
    );
  }
  if (view === "main_opened") return <>{button("Done, carry on", actions.clear, true)}{button("Give up", actions.giveUp)}</>;
  if (signIn) {
    return (
      <>
        {button("Take control", () => actions.openSignIn(live), true)}
        {button("Later", actions.later)}
        {field ? null : (
          <button type="button" className="btn btn--ghost btn--small" disabled={actions.busy}
            onClick={() => void actions.checkAgain()}>Check again</button>
        )}
      </>
    );
  }
  return (
    <>
      {button("Take control", actions.takeControl, !(data.suggest_main_browser && data.url))}
      {button("Try again", actions.clear)}
      {data.url ? button("Use my main Brave", actions.openInMain, data.suggest_main_browser) : null}
      {button("Give up", actions.giveUp)}
    </>
  );
}

// A Sign-in card's words: the site's sign-in page, whose computer, what to type, and the promise.
export function signInExplanation(host: string, botName: string): string {
  return `${host}'s sign-in page is open on ${botName}'s computer. Take control, type your email and password, `
    + `then press I'm done. ${NEVER_SEES_PASSWORD}`;
}

function StuckBody({ view, data, botName, tainted, actions, signIn, screen, field }: {
  view: View; data: StuckMessageData; botName: string; tainted: boolean; actions: Actions; signIn: boolean;
  screen: ReactNode; // the Sign-in card's live screen, when it shows in the chat
  field: SecretFieldKind | null; // B3: the masked field, while the card waits for it
}) {
  const { error } = actions;
  if (view === "holding" && actions.asking) {
    return (
      <>
        {screen}
        <GiveBackForm host={data.host || undefined} signIn busy={actions.busy} error={error}
          onConfirm={(account, keep) => void actions.giveBack(account, keep)} onBack={() => actions.ask(false)} />
      </>
    );
  }
  return (
    <>
      {screen}
      {field && view === "open" ? (
        <SecretField host={data.host} kind={field} busy={actions.busy} onSend={actions.typeSecret} />
      ) : null}
      {data.url && !signIn ? <p className="stuck-card__url"><bdi dir="ltr">{data.url}</bdi></p> : null}
      {tainted && data.url && !signIn ? <p className="fold-card__taint" role="note">{TAINT_NOTE}</p> : null}
      {view === "holding" && !screen ? (
        <p className="stuck-card__state">{`You have control. Clear it in ${botName}'s window, then give it back.`}</p>
      ) : null}
      {view === "main_opened" ? <p className="stuck-card__state">Opened in your main Brave.</p> : null}
      {error ? <ErrorNotice message={error} /> : null}
    </>
  );
}

// Where a Sign-in card shows its computer. Its bot must be at hand, and the bot's Computer tab must not be open
// beside the chat: that tab has its own live screen and Take control, and the page keeps one socket per bot.
function useLiveWhere(bot: BotOut | undefined): LiveWhere {
  const phone = useMediaQuery(PHONE_QUERY);
  const [params] = useSearchParams();
  if (!bot || params.get("panel") === "computer") return "panel";
  return phone ? "sheet" : "inline";
}

// The live screen a Sign-in card shows in the chat: the preview while it waits, the control view once you hold it.
function signInScreen(bot: BotOut | undefined, live: LiveWhere, view: View, actions: Actions): ReactNode {
  if (!bot || live === "panel" || actions.full) return null;
  if (view === "open") return <SignInPreview bot={bot} />;
  if (view === "holding" && live === "inline") return <SignInInline bot={bot} onControlEnded={actions.closeControl} />;
  return null;
}

export function StuckCard({ data, card, botName, tainted, bot, onReply }: StuckCardProps) {
  const actions = useStuckActions(data.card_id, data.bot_id, card?.state === "open");
  const live = useLiveWhere(bot);
  const shown = latest(card, actions.answered);
  if (!shown) return <div className="message__body">{data.line}</div>;
  const state = shown.state;
  if (state !== "open") {
    // A card with no site (the bot asked for help before any page), or one you answered in the chat, folds to the
    // bare words.
    const { word } = FOLDED[state];
    const line = data.host && state !== "replied" ? `${word}: ${data.host}` : word;
    // A blocked card is the bot's last word ("do it yourself"): it keeps the way in, Take control.
    const action = state === "blocked" ? (
      <button type="button" className="btn btn--quiet btn--small" disabled={actions.busy}
        onClick={() => void actions.takeControl()}>Take control</button>
    ) : undefined;
    return <FoldedLine icon={FOLDED[state].icon} ariaLabel={line} action={action}>{line}</FoldedLine>;
  }
  const view: View = actions.holding ? "holding" : shown.main_opened ? "main_opened" : "open";
  const signIn = Boolean(data.sign_in || shown.sign_in);
  const title = stuckTitle(data.host, data.url, signIn);
  const screen = signIn ? signInScreen(bot, live, view, actions) : null;
  const field = signIn && data.host ? (shown.secret_field ?? data.secret_field ?? null) : null;
  const hasBody = Boolean(data.url && !signIn) || view !== "open" || actions.error !== null || screen !== null
    || field !== null;
  const asking = signIn && view === "holding" && actions.asking;
  const explanation = field ? secretExplanation(data.host, field, botName)
    : signIn && data.host ? signInExplanation(data.host, botName) : data.line;
  const wide = view === "holding" && screen !== null;
  return (
    <FoldCard ariaLabel={title} title={title} explanation={explanation} className={wide ? "fold-card--wide" : undefined}
      footer={asking ? undefined : (
        <>
          <StuckFooter view={view} data={data} actions={actions} signIn={signIn} live={live} field={field !== null} />
          {onReply ? (
            <button type="button" className="btn btn--ghost btn--small" disabled={actions.busy}
              onClick={onReply}>Reply</button>
          ) : null}
        </>
      )}>
      {hasBody ? (
        <StuckBody view={view} data={data} botName={botName} tainted={tainted} actions={actions} signIn={signIn}
          screen={screen} field={field} />
      ) : null}
      {signIn && bot && live !== "panel" && view === "holding" && actions.full ? (
        <SignInFullScreen bot={bot} card={shown} onClosed={actions.closeControl} />
      ) : null}
    </FoldCard>
  );
}
