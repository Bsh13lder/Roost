import { useState, type FormEvent } from "react";
import { ErrorNotice } from "../ErrorNotice";
import * as botsApi from "../../api/bots";
import { describeError } from "../../api/client";
import type { BotOut } from "../../api/types";
import { checkGroup } from "../../lib/botFields";
import { BOT_LIMITS } from "../../lib/botProfile";
import { Button } from "../../ui/Button";
import { Chip } from "../../ui/Chip";
import { Input } from "../../ui/Input";
import { Popover } from "../../ui/Popover";

interface GroupLabelProps {
  bot: BotOut;
  labels: readonly string[]; // the labels other bots use, offered in one tap
  onChange: (bot: BotOut) => void;
}

// The bot's sidebar label (polish R1.4): a chip under the job that opens a small popover. A refusal
// is said under the field and the text stays; nothing is asked of the server for a label that is
// too long or runs over two lines.
export function GroupLabel({ bot, labels, onChange }: GroupLabelProps) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const changeOpen = (next: boolean) => {
    setOpen(next);
    setError(null);
    if (next) setText(bot.group ?? "");
  };

  const save = async (value: string) => {
    const problem = checkGroup(value);
    if (problem) return setError(problem);
    setBusy(true);
    setError(null);
    try {
      onChange(await botsApi.updateBot(bot.id, { group: value.trim() }));
      setOpen(false);
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusy(false);
    }
  };

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    void save(text);
  };

  return (
    <Popover open={open} onOpenChange={changeOpen} label="Label" align="center"
      trigger={<Chip className={bot.group ? "group-label" : "group-label group-label--quiet"}>{bot.group ?? "Add a label"}</Chip>}>
      <form className="group-label__form" onSubmit={onSubmit}>
        <label className="group-label__field">
          <span className="group-label__caption">Label</span>
          <Input controlSize="md" value={text} maxLength={BOT_LIMITS.group} autoFocus
            onChange={(event) => setText(event.target.value)} />
        </label>
        {labels.length > 0 ? (
          <div className="group-label__used">
            {labels.map((label) => (
              <Chip key={label} size="sm" disabled={busy} onClick={() => void save(label)}>{label}</Chip>
            ))}
          </div>
        ) : null}
        {error ? <ErrorNotice message={error} /> : null}
        <div className="group-label__actions">
          {bot.group ? <Button variant="ghost" size="sm" disabled={busy} onClick={() => void save("")}>Remove label</Button> : null}
          <Button type="submit" variant="primary" size="sm" loading={busy}>Save</Button>
        </div>
      </form>
    </Popover>
  );
}
