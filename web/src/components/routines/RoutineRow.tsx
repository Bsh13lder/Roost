import { useState, type ReactNode } from "react";
import { MoreIcon } from "../icons";
import { Badge } from "../../ui/Badge";
import { Button } from "../../ui/Button";
import { Menu, MenuItem } from "../../ui/Menu";
import { Switch } from "../../ui/Switch";
import { describeError } from "../../api/client";
import * as routinesApi from "../../api/routines";
import type { RoutineOut } from "../../api/routines";
import { BUILTIN_TITLE } from "./constants";
import { zoneClock, zoneStamp, nextRunWords } from "./zoneTime";

// "Watching web.whatsapp.com · every 5 min · last change 14:50" for a watching routine; "" for any other.
export function watchLine(routine: RoutineOut): string {
  const watch = routine.watch;
  if (!watch) return "";
  const head = `Watching ${watch.host} · every ${watch.every_min} min`;
  const changed = zoneClock(watch.last_changed_at);
  return changed ? `${head} · last change ${changed}` : head;
}

type Asking = "run" | "delete" | null;

export interface RoutineRowProps {
  routine: RoutineOut;
  onChanged: (routine: RoutineOut) => void;
  onRemoved: (id: string) => void;
  onEdit: (routine: RoutineOut) => void;
  onHistory: (routine: RoutineOut) => void;
  extra?: ReactNode; // a line under the schedule (the Routines page: the last result)
}

const CONFIRM: Record<"run" | "delete", { yes: string; question: (name: string) => string }> = {
  run: { yes: "Yes, run it now", question: (name) => `Run “${name}” now?` },
  delete: { yes: "Yes, delete it", question: (name) => `Delete “${name}”? Its history goes with it.` },
};

// One routine: its name, its schedule in words, when it runs next in words ("in 3 h"), a switch and a menu. Run now
// and Delete ask first; an old end-of-day summary can be re-timed, switched or deleted like any routine.
export function RoutineRow({ routine, onChanged, onRemoved, onEdit, onHistory, extra }: RoutineRowProps) {
  const [asking, setAsking] = useState<Asking>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const builtin = routine.builtin !== null;
  const title = builtin ? BUILTIN_TITLE : routine.name;
  const next = routine.enabled ? nextRunWords(routine.next_run_at) : "";

  const attempt = async (work: () => Promise<void>) => {
    setBusy(true);
    setMessage(null);
    try { await work(); } catch (err) { setMessage(describeError(err)); } finally { setBusy(false); }
  };
  const toggle = (enabled: boolean) => attempt(async () => onChanged(await routinesApi.patchRoutine(routine.id, { enabled })));
  const confirm = () => attempt(async () => {
    const what = asking;
    setAsking(null);
    if (what === "run") { await routinesApi.runRoutineNow(routine.id); setMessage("Started. The Report will follow."); }
    if (what === "delete") { await routinesApi.deleteRoutine(routine.id); onRemoved(routine.id); }
  });

  return (
    <li className="routine-row">
      <div className="routine-row__main">
        <p className="routine-row__name">
          {title}
          {routine.tainted ? <Badge tone="danger" className="routine-row__taint">from web content</Badge> : null}
        </p>
        <p className="routine-row__words">{watchLine(routine) || routine.words}</p>
        {next ? (
          <p className="routine-row__next" title={zoneStamp(routine.next_run_at)}>
            {routine.watch ? "Next check" : "Next run"}: {next}
          </p>
        ) : null}
        {extra}
      </div>
      <Switch checked={routine.enabled} disabled={busy} onChange={(on) => void toggle(on)}>
        <span className="sr-only">{`${title} ${routine.enabled ? "on" : "off"}`}</span>
      </Switch>
      <Menu label={`More for ${title}`} trigger={<MoreIcon />}>
        <MenuItem onSelect={() => setAsking("run")}>Run now</MenuItem>
        <MenuItem onSelect={() => onEdit(routine)}>Edit</MenuItem>
        <MenuItem onSelect={() => onHistory(routine)}>History</MenuItem>
        <MenuItem danger onSelect={() => setAsking("delete")}>Delete</MenuItem>
      </Menu>
      {asking ? (
        <div className="routine-row__ask" role="group" aria-label="Are you sure?">
          <p>{CONFIRM[asking].question(title)}</p>
          <Button size="sm" variant={asking === "delete" ? "danger" : "primary"} loading={busy} onClick={() => void confirm()}>
            {CONFIRM[asking].yes}
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setAsking(null)}>Cancel</Button>
        </div>
      ) : null}
      {message ? <p className="routine-row__note" role="status">{message}</p> : null}
    </li>
  );
}
