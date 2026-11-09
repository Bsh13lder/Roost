import type { AvatarOut } from "../../api/types";
import { usePrefersReducedMotion } from "../../hooks/usePrefersReducedMotion";
import { RobotFace } from "../robot/RobotFace";
import { botRole, lensbotShape } from "../robot/look";
import { doingOf } from "../robot/moments";
import { WORKING_BOT_PX } from "./constants";

export interface WorkingBotProps {
  avatar: AvatarOut | undefined;
  kind: string | null | undefined; // the running step's kind (RunStepKind); none is thinking
}

// A working bot in its chat (owner, 2026-10-27, like Grok's moving mark): its own Lensbot, drawn just large
// enough to be live, bobbing as On it does, with its eyes acting out what it is doing (robot-doing.css).
// Its words sit beside it, so the drawing is decorative.
export function WorkingBot({ avatar, kind }: WorkingBotProps) {
  const still = usePrefersReducedMotion();
  if (!avatar) return null;
  return (
    <RobotFace className="working-bot" shape={lensbotShape(avatar.shape)} role={botRole(avatar.role)} color={avatar.color}
      moment="onit" size={WORKING_BOT_PX} still={still} picture={avatar.picture} doing={doingOf(kind)} />
  );
}
