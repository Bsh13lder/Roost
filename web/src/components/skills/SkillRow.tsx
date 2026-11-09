import { Badge } from "../../ui/Badge";
import { Switch } from "../../ui/Switch";
import type { SkillOut } from "../../api/skills";
import { MARK, ON_FOR_BOT } from "./constants";

export interface SkillRowProps {
  skill: SkillOut;
  busy: boolean;
  onToggle: (skill: SkillOut, on: boolean) => void;
  onOpen: (skill: SkillOut) => void;
}

// One skill on the Info tab: its name, Use when underneath, the web mark, and its switch for this bot.
// The row's text opens the editor.
export function SkillRow({ skill, busy, onToggle, onOpen }: SkillRowProps) {
  return (
    <li className="skill-row">
      <button type="button" className="skill-row__main" onClick={() => onOpen(skill)}>
        <span className="skill-row__name">
          {skill.name}
          {skill.tainted ? <Badge tone="danger" className="skill-row__mark">{MARK}</Badge> : null}
        </span>
        <span className="skill-row__when">{skill.use_when}</span>
      </button>
      <Switch checked={skill.on ?? true} disabled={busy} onChange={(on) => onToggle(skill, on)}>
        <span className="sr-only">{`${ON_FOR_BOT}: ${skill.name}`}</span>
      </Switch>
    </li>
  );
}
