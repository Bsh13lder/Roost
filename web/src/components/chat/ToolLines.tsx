import { useState } from "react";
import { toolLineText } from "../../lib/toolLines";
import { cx } from "../../ui/cx";
import { CheckIcon } from "../icons";
import { TOOL_LINES_SHOWN } from "./constants";

export interface ToolLinesProps {
  lines: readonly string[]; // the bot's activities for this reply, oldest first (store/live.ts toolLines)
  working: boolean; // the reply is still being written: its last line is the current step
  textLength?: number; // how much of the reply's text has come in so far
}

// The last step is the current one while the reply is being written and none of its words have come since
// that step began (final-review fix): once the text streams after it, the step is done, before the reply
// settles. A step the bot starts after some words is current until more words come.
function useLastStepCurrent(steps: number, textLength: number, working: boolean): boolean {
  const [mark, setMark] = useState({ steps, textLength });
  const begun = mark.steps === steps ? mark : { steps, textLength };
  if (begun !== mark) setMark(begun);
  return working && textLength <= begun.textLength;
}

// What the bot did for this reply (redesign P2), one compact line per step: the latest few, with a count
// of the earlier ones. Live only; P4 turns them into record cards.
export function ToolLines({ lines, working, textLength = 0 }: ToolLinesProps) {
  const lastCurrent = useLastStepCurrent(lines.length, textLength, working);
  const earlier = Math.max(0, lines.length - TOOL_LINES_SHOWN);
  const shown = lines.slice(earlier);
  return (
    <ul className="tool-lines" aria-label="Steps">
      {earlier > 0 ? <li className="tool-line tool-line--earlier">{`${earlier} earlier ${earlier === 1 ? "step" : "steps"}`}</li> : null}
      {shown.map((activity, index) => {
        const current = lastCurrent && index === shown.length - 1;
        return (
          <li key={earlier + index} className={cx("tool-line", current && "tool-line--current")}>
            <span className="tool-line__mark" aria-hidden="true">
              {current ? <span className="tool-line__spinner" /> : <CheckIcon />}
            </span>
            {toolLineText(activity, !current)}
          </li>
        );
      })}
    </ul>
  );
}
