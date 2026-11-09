import { useState } from "react";
import { Menu, MenuRadioGroup, MenuRadioItem } from "../../ui/Menu";
import { setApproval } from "../../api/bots";
import { describeError } from "../../api/client";
import type { BotOut } from "../../api/types";
import { approvalFor, chatModeOf, chatModeOption, type ChatMode } from "../../lib/chatMode";
import { CHAT_MODE_OPTIONS, CHAT_MODE_TITLE } from "../approvals/constants";

// The chat mode pill (owner decision 2026-10-25), inside the composer beside the +: the current mode's name, and one
// tap opens the three with their lines. Each pick is one save; the bot the server sends back replaces this one, and a
// failed save is said in the chat's notice while the pill keeps showing the old mode.
export function ChatModePill({ bot, onChange, onError }: {
  bot: BotOut; onChange: (bot: BotOut) => void; onError: (message: string | null) => void;
}) {
  const [busy, setBusy] = useState(false);
  const current = chatModeOf(bot);
  const choose = async (mode: ChatMode) => {
    if (mode === current || busy) return;
    const next = approvalFor(bot, mode);
    setBusy(true);
    onError(null);
    try {
      onChange(await setApproval(bot.id, next.mode, next.askTopics, next.autoReview));
    } catch (err) {
      onError(describeError(err));
    } finally {
      setBusy(false);
    }
  };
  const label = chatModeOption(current).label;
  return (
    <Menu label={`${CHAT_MODE_TITLE}: ${label}`} side="top" align="start" triggerClassName="chat-mode__pill"
      trigger={<span className="chat-mode__label">{label}</span>}>
      <MenuRadioGroup value={current} onValueChange={(mode) => void choose(mode)}>
        {CHAT_MODE_OPTIONS.map((option) => (
          <MenuRadioItem key={option.id} value={option.id} disabled={busy}>
            <span className="chat-mode__text">
              <span className="chat-mode__name">{option.label}</span>
              <span className="chat-mode__line">{option.description}</span>
            </span>
          </MenuRadioItem>
        ))}
      </MenuRadioGroup>
    </Menu>
  );
}
