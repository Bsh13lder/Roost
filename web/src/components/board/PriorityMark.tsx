import { FlagIcon } from "../icons";
import type { TaskOut } from "../../api/types";

export interface PriorityMarkProps {
  priority: TaskOut["priority"];
  size?: "row" | "pill" | "icon"; // icon: only the urgent flag, nothing else (a calendar pill)
}

// Amendment G: urgent is a red pill with a flag and the word, high is a warm flag, medium and low show nothing.
// Typing keeps !!! and the like; the display never shows them.
export function PriorityMark({ priority, size = "row" }: PriorityMarkProps) {
  if (size === "icon") {
    return priority === "urgent" ? <span className="prio prio--urgent prio--icon" title="Urgent"><FlagIcon /></span> : null;
  }
  if (priority === "urgent") {
    return <span className={`prio prio--urgent prio--${size}`} title="Urgent"><FlagIcon />Urgent</span>;
  }
  if (priority === "high") {
    return <span className={`prio prio--high prio--${size}`} title="High"><FlagIcon />{size === "pill" ? "High" : null}</span>;
  }
  return null;
}
