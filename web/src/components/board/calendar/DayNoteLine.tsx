import type { DayNoteOut } from "../../../api/dayNotes";
import { CloseIcon } from "../../icons";
import { RobotFace } from "../../robot/RobotFace";
import { botRole, lensbotShape } from "../../robot/look";
import { useLiveState } from "../../../hooks/useLiveStore";
import { IconButton } from "../../../ui/IconButton";
import { WebContentChip } from "../WebContentChip";

const ROBOT_PX = 14;

export interface DayNoteLineProps {
  note: DayNoteOut;
  onDelete: (note: DayNoteOut) => void;
}

// Who wrote a note: "You" in bold, or a small robot in the bot's colour and the bot's name.
function Who({ note }: { note: DayNoteOut }) {
  const bots = useLiveState().bots;
  if (note.author_kind === "user") return <span className="dwho dwho--you">You</span>;
  const bot = note.bot_id ? bots[note.bot_id] : undefined;
  return (
    <span className="dwho">
      {bot ? <RobotFace shape={lensbotShape(bot.avatar.shape)} role={botRole(bot.avatar.role)} color={bot.avatar.color} size={ROBOT_PX} still picture={bot.avatar.picture} />
        : <span className="dmini" aria-hidden="true" />}
      {note.bot_name ?? "A bot"}
    </span>
  );
}

// One line of a day's note (G11): who wrote it, then the text. The text is React text only, never markup: a bot may
// have read a web page. A bot's line that came from web content wears the "from web content" mark. ✕ deletes it.
export function DayNoteLine({ note, onDelete }: DayNoteLineProps) {
  return (
    <div className="dnote">
      <Who note={note} />
      <span className="dnote__text">{note.text}</span>
      {note.author_kind === "bot" && note.tainted ? <WebContentChip what="this note" /> : null}
      <IconButton className="dnote__del" size="sm" tooltip={false} label="Delete note" icon={<CloseIcon />}
        onClick={() => onDelete(note)} />
    </div>
  );
}
