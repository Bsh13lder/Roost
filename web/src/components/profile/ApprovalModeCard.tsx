import { useState } from "react";
import { ErrorNotice } from "../ErrorNotice";
import { Segmented } from "../../ui/Segmented";
import { Switch } from "../../ui/Switch";
import { setApproval } from "../../api/bots";
import { describeError } from "../../api/client";
import type { ApprovalMode, ApprovalTopic, BotOut } from "../../api/types";
import { approvalFor, chatModeOf, chatModeOption, type ChatMode } from "../../lib/chatMode";
import {
  ALWAYS_ASK_TITLE, CHAT_MODE_OPTIONS, LOCKED_TOPIC_LABEL, LOCKED_TOPIC_NOTE, MODE_OPTIONS, TOPIC_LABELS,
  TOPIC_OPTIONS,
} from "../approvals/constants";

// C3: Browsing actions, for a bot on its Linux computer: the same three states as the chat's mode pill (owner
// decision 2026-10-25; lib/chatMode.ts reads and writes them). Buying, sending and submitting ask in every one.
function BrowsingRow({ value, busy, onChange }: { value: ChatMode; busy: boolean; onChange: (mode: ChatMode) => void }) {
  return (
    <div className="info-row">
      <span className="info-row__label">{TOPIC_LABELS.browsing}</span>
      <fieldset className="approval-card__group" disabled={busy}>
        <Segmented label={TOPIC_LABELS.browsing} options={CHAT_MODE_OPTIONS} value={value}
          onChange={(id) => { if (id !== value) onChange(id); }} />
      </fieldset>
      <p className="info-row__hint">{chatModeOption(value).description}</p>
    </div>
  );
}

// The Info tab's mode card: what the bot may just do, and what waits for your OK. Every press saves at once; a
// failed save is said here and the old mode stays (the card only shows what the server last sent).
export function ApprovalModeCard({ bot, onChange }: { bot: BotOut; onChange: (bot: BotOut) => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { mode, ask_topics: topics } = bot.approval;
  // `autoReview` only from the Browsing actions row; the other controls leave the stored value alone.
  const save = async (nextMode: ApprovalMode, nextTopics: readonly ApprovalTopic[], autoReview?: boolean) => {
    setBusy(true);
    setError(null);
    try {
      onChange(await (autoReview === undefined
        ? setApproval(bot.id, nextMode, nextTopics)
        : setApproval(bot.id, nextMode, nextTopics, autoReview)));
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusy(false);
    }
  };
  const toggle = (topic: ApprovalTopic, on: boolean) =>
    save(mode, on ? [...topics, topic] : topics.filter((t) => t !== topic));
  const described = MODE_OPTIONS.find((option) => option.id === mode);
  return (
    <section className="info-card approval-card" aria-label="Approval mode">
      <div className="info-row">
        <span className="info-row__label">Approval mode</span>
        <fieldset className="approval-card__group" disabled={busy}>
          <Segmented label="Approval mode" options={MODE_OPTIONS} value={mode} onChange={(id) => void save(id, topics)} />
        </fieldset>
        {described ? <p className="info-row__hint">{described.description}</p> : null}
      </div>
      {bot.computer === "linux" ? (
        <BrowsingRow value={chatModeOf(bot)} busy={busy} onChange={(next) => {
          const chosen = approvalFor(bot, next);
          void save(chosen.mode, chosen.askTopics, chosen.autoReview);
        }} />
      ) : null}
      <div className="info-row">
        <span className="info-row__label">{ALWAYS_ASK_TITLE}</span>
        <ul className="approval-card__topics">
          {TOPIC_OPTIONS.map((topic) => (
            <li key={topic.id}>
              <Switch checked={topics.includes(topic.id)} disabled={busy} onChange={(on) => void toggle(topic.id, on)}>
                {topic.label}
              </Switch>
            </li>
          ))}
          <li>
            <Switch checked disabled onChange={() => undefined}>
              {LOCKED_TOPIC_LABEL} <span className="approval-card__note">· {LOCKED_TOPIC_NOTE}</span>
            </Switch>
          </li>
        </ul>
      </div>
      {error ? <div className="info-row"><ErrorNotice message={error} /></div> : null}
    </section>
  );
}
