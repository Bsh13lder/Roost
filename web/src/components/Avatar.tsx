import { usePrefersReducedMotion } from "../hooks/usePrefersReducedMotion";
import { useBotEvent, useBotThinking } from "../hooks/useRobotEvents";
import { cx } from "../ui/cx";
import { RobotFace } from "./robot/RobotFace";
import { botRole, lensbotShape } from "./robot/look";
import { STATUS_MOMENT, type RobotMoment } from "./robot/moments";
import { STATUS_LABELS, StatusLabel } from "./StatusLabel";
import type { AvatarOut, BotStatus } from "../api/types";

// A bot's avatar (avatars v7): its Lensbot, whose eyes and posture show the status and whose body wears
// its role, and the status in words beside it (spec 7.3: colour is never the only signal). Any stored
// shape draws: an old ghost, head or bird maps to a Lensbot (robot/look.ts). Reduced motion stills it; `avatar--reduced-motion` lets tests see it.
export interface AvatarProps {
  avatar: AvatarOut;
  status: BotStatus;
  activity?: string | null;
  size?: number;
  // `label={false}` drops the words under the robot: only for callers that show StatusLabel beside it.
  label?: boolean;
  // A repeat of a bot named nearby (message avatars): hidden from assistive tech.
  decorative?: boolean;
  // The main bot wears a star (S1.4); no other bot does.
  star?: boolean;
  // A posture instead of the status's own (the Computer tab's sleeping robot).
  moment?: RobotMoment;
  // Given, the robot plays its bot's live events (Created something, Done, New message, Thinking, the Stuck glitch).
  botId?: string;
  // A click squishes it: the panel hero and the pinned tiles, never a plain list row.
  poke?: boolean;
  // The eyes on top of an uploaded picture (off by default).
  pictureEyes?: boolean;
  // Waiting for you to take control (a Stuck bot): the hand glyph on its face.
  control?: boolean;
}

export function Avatar({
  avatar, status, activity = null, size = 96, label = true, decorative = false, star = false, moment, botId, poke = false,
  pictureEyes = false, control = false,
}: AvatarProps) {
  const reducedMotion = usePrefersReducedMotion();
  const event = useBotEvent(botId);
  const thinking = useBotThinking(botId);
  return (
    <div className="avatar-wrap">
      <RobotFace className={cx("avatar", `avatar--${status}`, reducedMotion && "avatar--reduced-motion")}
        shape={lensbotShape(avatar.shape)} role={botRole(avatar.role)} color={avatar.color} moment={moment ?? STATUS_MOMENT[status]} star={star} size={size}
        still={reducedMotion} picture={avatar.picture} pictureEyes={pictureEyes} event={event} thinking={thinking} control={control} poke={poke}
        title={decorative ? undefined : STATUS_LABELS[status]} />
      {label ? <StatusLabel status={status} activity={activity} /> : null}
    </div>
  );
}
