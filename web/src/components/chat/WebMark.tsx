import { useState } from "react";
import { GlobeIcon } from "../icons";
import { Popover } from "../../ui/Popover";
import { cx } from "../../ui/cx";
import { WEB_MARK_EXPLAINED, WEB_MARK_LABEL, WEB_MARK_NAME } from "./constants";

// The "from web content" mark in the chat (2026-10-26, owner: "lets upgrade little the quality of that web content
// mark"): a small quiet chip, a globe and "Web", under the text it marks. A tap or click says what it means; the
// hover title says it too. Same honesty as the old orange words, less noise.
export function WebMark({ className }: { className?: string }) {
  const [open, setOpen] = useState(false);
  return (
    <Popover label={WEB_MARK_NAME} open={open} onOpenChange={setOpen} align="start" side="top"
      trigger={(
        <button type="button" className={cx("web-mark", className)} aria-label={WEB_MARK_NAME} title={WEB_MARK_EXPLAINED}>
          <GlobeIcon />
          <span aria-hidden="true">{WEB_MARK_LABEL}</span>
        </button>
      )}>
      <p className="web-mark__explained">{WEB_MARK_EXPLAINED}</p>
    </Popover>
  );
}
