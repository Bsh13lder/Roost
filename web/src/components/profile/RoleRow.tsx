import { useId } from "react";
import { BOT_ROLES, ROLE_LABELS } from "../robot/look";
import { suggestRole } from "../robot/roles";
import { Chip } from "../../ui/Chip";
import { cx } from "../../ui/cx";
import type { BotRole } from "../../api/types";

export interface RoleRowProps {
  role: BotRole | null | undefined; // the stored role; none counts as general but is not pressed
  job: string; // the bot's job: with no role set, its words suggest one
  disabled?: boolean;
  onPick: (role: BotRole) => void;
}

// The look card's Role row (avatars v7 role looks): eight small chips; the bot's own is pressed. With no
// role set, the job's words suggest one: its chip is marked and a line names it. Nothing is saved until
// the user clicks a chip.
export function RoleRow({ role, job, disabled = false, onPick }: RoleRowProps) {
  const hintId = useId();
  const suggested = role ? null : suggestRole(job);
  return (
    <fieldset className="role-row">
      <legend className="field__label">Role</legend>
      <div className="role-row__chips">
        {BOT_ROLES.map((one) => (
          <Chip key={one} size="sm" selected={role === one} disabled={disabled}
            className={cx(suggested === one && "chip--suggested")}
            aria-describedby={suggested === one ? hintId : undefined} onClick={() => onPick(one)}>
            {ROLE_LABELS[one]}
          </Chip>
        ))}
      </div>
      {suggested ? <p id={hintId} className="role-row__hint">Suggested from its job: {ROLE_LABELS[suggested]}</p> : null}
    </fieldset>
  );
}
