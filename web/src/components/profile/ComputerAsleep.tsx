import { Avatar } from "../Avatar";
import { Button } from "../../ui/Button";
import { cx } from "../../ui/cx";
import { usePrefersReducedMotion } from "../../hooks/usePrefersReducedMotion";
import type { BotOut } from "../../api/types";

const Z_MARKS = [0, 1, 2] as const;

// The Computer tab's sleeping state (polish R1.13): the bot's own robot with its screen off, three z
// marks drifting up, and the way to wake it. The marks stand still under reduced motion.
export function ComputerAsleep({ bot, onOpen }: { bot: BotOut; onOpen: () => void }) {
  const still = usePrefersReducedMotion();
  return (
    <div className={cx("computer-asleep", still && "computer-asleep--still")}>
      <div className="computer-asleep__robot">
        <Avatar avatar={bot.avatar} status={bot.status} moment="off" size={72} label={false} decorative />
        {Z_MARKS.map((mark) => (
          <span key={mark} className="computer-asleep__z" aria-hidden="true">z</span>
        ))}
      </div>
      <h3 className="computer-asleep__title">Computer is asleep</h3>
      <p className="computer-asleep__line">{bot.name}&apos;s computer wakes when it needs it.</p>
      <Button variant="primary" size="sm" onClick={onOpen}>Open it</Button>
    </div>
  );
}
