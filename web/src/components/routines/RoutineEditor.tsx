import { useState } from "react";
import { Button } from "../../ui/Button";
import { Field } from "../../ui/Field";
import { Input } from "../../ui/Input";
import { Sheet } from "../../ui/Sheet";
import { Textarea } from "../../ui/Textarea";
import { describeError } from "../../api/client";
import * as routinesApi from "../../api/routines";
import type { RoutineDraftIn, RoutineOut, ScheduleIn } from "../../api/routines";
import { BUILTIN_TITLE, DEFAULT_TIME, WORKDAYS } from "./constants";
import { ScheduleFields } from "./ScheduleFields";
import { StandingPermissions } from "./StandingPermissions";
import { RoutineModelField } from "./RoutineModelField";
import { WatchFields, watchDraft, watchIn, type WatchDraft } from "./WatchFields";

export interface RoutineEditorProps {
  botId: string;
  routine: RoutineOut | null; // null: a new one
  onClose: () => void;
  onSaved: (routine: RoutineOut) => void;
}

const NEW_SCHEDULE: ScheduleIn = { kind: "times", days: WORKDAYS, times: [DEFAULT_TIME] };

// The watch part of a save: only sent when it is on, or to switch an existing watch off (null).
function watchChange(routine: RoutineOut | null, draft: WatchDraft): Pick<RoutineDraftIn, "watch"> {
  const watch = watchIn(draft);
  if (watch !== null) return { watch };
  return routine?.watch ? { watch: null } : {};
}

// A routine's form in a Sheet. The built-in end-of-day summary can only be re-timed, so it shows the schedule alone.
// A watching routine runs only when its page changes, so its schedule is not shown.
export function RoutineEditor({ botId, routine, onClose, onSaved }: RoutineEditorProps) {
  const builtin = routine?.builtin != null;
  const [name, setName] = useState(routine?.name ?? "");
  const [instructions, setInstructions] = useState(routine?.instructions ?? "");
  const [schedule, setSchedule] = useState<ScheduleIn>(routine?.schedule ?? NEW_SCHEDULE);
  const [watch, setWatch] = useState<WatchDraft>(watchDraft(routine?.watch));
  const [model, setModel] = useState<string | null>(routine?.model ?? null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      const fields = { name, instructions, schedule, model, ...watchChange(routine, watch) };
      const saved = routine === null
        ? await routinesApi.createRoutine(botId, fields)
        : await routinesApi.patchRoutine(routine.id, builtin ? { schedule } : fields);
      onSaved(saved);
    } catch (err) {
      setError(describeError(err));
    } finally {
      setSaving(false);
    }
  };
  return (
    <Sheet open title={builtin ? BUILTIN_TITLE : routine ? "Edit routine" : "New routine"} onOpenChange={(open) => { if (!open) onClose(); }}
      footer={(
        <>
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button variant="primary" loading={saving} onClick={() => void save()}>Save</Button>
        </>
      )}>
      <div className="routine-editor">
        {builtin ? null : (
          <>
            <Field label="Name"><Input value={name} onChange={(event) => setName(event.target.value)} /></Field>
            <Field label="What to do"><Textarea value={instructions} onChange={(event) => setInstructions(event.target.value)} /></Field>
            <WatchFields value={watch} onChange={setWatch} />
            <RoutineModelField value={model} onChange={setModel} />
          </>
        )}
        {watch.on && !builtin ? null : <ScheduleFields value={schedule} onChange={setSchedule} />}
        {error ? <p className="routine-editor__error" role="alert">{error}</p> : null}
        {routine !== null && !builtin ? <StandingPermissions routineId={routine.id} /> : null}
      </div>
    </Sheet>
  );
}
