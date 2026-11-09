import { useState } from "react";
import { ErrorNotice } from "../ErrorNotice";
import { Segmented } from "../../ui/Segmented";
import * as botsApi from "../../api/bots";
import { describeError } from "../../api/client";
import type { BotOut, ComputerKind } from "../../api/types";
import { KIND_LABELS, KIND_LINES, MAC_BRAVE_RISK_LINE } from "./constants";

const OPTIONS = (Object.keys(KIND_LABELS) as ComputerKind[]).map((id) => ({ id, label: KIND_LABELS[id] }));

// Computer: Linux computer | Mac Brave (optional). A bot starts on its Linux computer, the usual choice;
// Mac Brave is the optional one.
// The server stops the old kind when it changes; a refusal is said and the old choice stays.
export function ComputerKindSwitch({ bot, onChange }: { bot: BotOut; onChange: (bot: BotOut) => void }) {
  const [error, setError] = useState<string | null>(null);
  const choose = async (kind: ComputerKind) => {
    if (kind === bot.computer) return;
    setError(null);
    try {
      onChange(await botsApi.setComputer(bot.id, kind));
    } catch (err) {
      setError(describeError(err));
    }
  };
  return (
    <div className="info-row computer-kind">
      <span className="info-row__label">Computer</span>
      <Segmented label="Computer" options={OPTIONS} value={bot.computer} onChange={(kind) => void choose(kind)} />
      <p className="info-row__hint">{KIND_LINES[bot.computer]}</p>
      {bot.computer === "mac_brave" ? <p className="info-row__hint">{MAC_BRAVE_RISK_LINE}</p> : null}
      {error ? <ErrorNotice message={error} /> : null}
    </div>
  );
}
