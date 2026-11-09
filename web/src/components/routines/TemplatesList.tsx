import { useEffect, useState } from "react";
import { Menu, MenuItem } from "../../ui/Menu";
import { describeError } from "../../api/client";
import * as routinesApi from "../../api/routines";
import type { RoutineOut, RoutineTemplateOut } from "../../api/routines";
import type { BotOut } from "../../api/types";
import { ErrorNotice } from "../ErrorNotice";

export interface TemplatesListProps {
  bots: readonly BotOut[];
  onAdded: () => void;
  onNeedsEdit: (botId: string, routine: RoutineOut) => void; // a template with a <placeholder> opens in the editor
}

const addedWords = (template: RoutineTemplateOut, bot: BotOut) => template.needs_edit
  ? `Added “${template.name}” to ${bot.name}, paused. Fill in its instructions, then switch it on.`
  : `Added “${template.name}” to ${bot.name}.`;

// Routine templates: a few ready routines; "Add to…" makes one on the bot you pick (switched on, yours to edit).
// A template that needs your words is added paused and opens in the editor.
export function TemplatesList({ bots, onAdded, onNeedsEdit }: TemplatesListProps) {
  const [templates, setTemplates] = useState<readonly RoutineTemplateOut[]>([]);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let current = true;
    routinesApi.listRoutineTemplates()
      .then((loaded) => { if (current) setTemplates(loaded); })
      .catch((err: unknown) => { if (current) setError(describeError(err)); });
    return () => { current = false; };
  }, []);

  const add = async (template: RoutineTemplateOut, bot: BotOut) => {
    setMessage(null);
    setError(null);
    try {
      const made = await routinesApi.addTemplate(bot.id, template.id);
      setMessage(addedWords(template, bot));
      onAdded();
      if (template.needs_edit) onNeedsEdit(bot.id, made);
    } catch (err) {
      setError(describeError(err));
    }
  };

  return (
    <>
      <ul className="routines__list">
        {templates.map((template) => (
          <li key={template.id} className="routine-row">
            <div className="routine-row__main">
              <p className="routine-row__name">{template.name}</p>
              <p className="routine-row__words">{template.words}</p>
              <p className="routine-row__next">{template.instructions}</p>
              {template.needs_edit ? <p className="routine-row__note">Paused until you fill it in</p> : null}
            </div>
            <Menu label={`Add ${template.name} to a bot`} trigger={<span className="routines-page__add">Add to…</span>}>
              {bots.map((bot) => (
                <MenuItem key={bot.id} onSelect={() => void add(template, bot)}>{`Add to ${bot.name}`}</MenuItem>
              ))}
            </Menu>
          </li>
        ))}
      </ul>
      {message ? <p className="routine-row__note" role="status">{message}</p> : null}
      {error ? <ErrorNotice message={error} /> : null}
    </>
  );
}
