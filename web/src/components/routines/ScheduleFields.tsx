import { useEffect, useState } from "react";
import { Button } from "../../ui/Button";
import { Input } from "../../ui/Input";
import { Segmented } from "../../ui/Segmented";
import { cx } from "../../ui/cx";
import { describeError } from "../../api/client";
import * as routinesApi from "../../api/routines";
import type { SchedulePreview, ScheduleIn } from "../../api/routines";
import { DEFAULT_TIME, PREVIEW_DEBOUNCE_MS, WEEKDAY_CHIPS } from "./constants";
import { zoneStamp } from "./zoneTime";
import { useAppTimeZone, zoneCity } from "../../lib/timeZone";

const KINDS = [{ id: "times", label: "Times" }, { id: "cron", label: "Custom" }] as const;

export interface ScheduleFieldsProps {
  value: ScheduleIn;
  onChange: (schedule: ScheduleIn) => void;
}

// What the schedule will do, asked of the server (no write) a moment after you stop typing: its words and the
// next five times on the account's clock, or the server's own sentence when it is not valid.
function usePreview(schedule: ScheduleIn) {
  const [preview, setPreview] = useState<SchedulePreview | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const key = JSON.stringify(schedule);
  useEffect(() => {
    let current = true;
    const timer = window.setTimeout(() => {
      routinesApi.previewSchedule(JSON.parse(key) as ScheduleIn)
        .then((shown) => { if (current) { setPreview(shown); setProblem(null); } })
        .catch((err: unknown) => { if (current) { setPreview(null); setProblem(describeError(err)); } });
    }, PREVIEW_DEBOUNCE_MS);
    return () => { current = false; window.clearTimeout(timer); };
  }, [key]);
  return { preview, problem };
}

function TimesFields({ value, onChange }: { value: Extract<ScheduleIn, { kind: "times" }>; onChange: (s: ScheduleIn) => void }) {
  const flip = (day: number) => {
    const days = value.days.includes(day) ? value.days.filter((d) => d !== day) : [...value.days, day].sort();
    onChange({ ...value, days });
  };
  const setTime = (index: number, time: string) =>
    onChange({ ...value, times: value.times.map((t, i) => (i === index ? time : t)) });
  return (
    <>
      <div className="schedule__days" role="group" aria-label="Days">
        {WEEKDAY_CHIPS.map(({ day, label }) => (
          <button key={day} type="button" className={cx("schedule__day", value.days.includes(day) && "is-on")}
            aria-pressed={value.days.includes(day)} onClick={() => flip(day)}>{label}</button>
        ))}
      </div>
      <ul className="schedule__times">
        {value.times.map((time, index) => (
          <li key={index}>
            <Input type="time" aria-label={`Time ${index + 1}`} controlSize="md" value={time}
              onChange={(event) => setTime(index, event.target.value)} />
            {value.times.length > 1 ? (
              <Button size="sm" variant="ghost" aria-label={`Remove time ${index + 1}`}
                onClick={() => onChange({ ...value, times: value.times.filter((_, i) => i !== index) })}>Remove</Button>
            ) : null}
          </li>
        ))}
      </ul>
      <Button size="sm" variant="ghost" onClick={() => onChange({ ...value, times: [...value.times, DEFAULT_TIME] })}>Add a time</Button>
    </>
  );
}

// The schedule part of the routine editor: Times (weekday chips and a list of times) or Custom (a cron line),
// and under it the live preview.
export function ScheduleFields({ value, onChange }: ScheduleFieldsProps) {
  const { preview, problem } = usePreview(value);
  const zone = useAppTimeZone();
  const pick = (kind: ScheduleIn["kind"]) => {
    if (kind === value.kind) return;
    onChange(kind === "cron" ? { kind: "cron", expr: "" } : { kind: "times", days: [1, 2, 3, 4, 5], times: [DEFAULT_TIME] });
  };
  return (
    <div className="schedule">
      <Segmented label="Schedule kind" options={KINDS} value={value.kind} onChange={pick} />
      {value.kind === "times" ? <TimesFields value={value} onChange={onChange} /> : (
        <label className="schedule__cron">
          <span>Cron</span>
          <Input value={value.expr} placeholder="0 8 * * 1-5" controlSize="md"
            onChange={(event) => onChange({ kind: "cron", expr: event.target.value })} />
        </label>
      )}
      <div className="schedule__preview" aria-live="polite">
        {problem ? <p className="schedule__problem" role="alert">{problem}</p> : null}
        {preview ? (
          <>
            <p className="schedule__words">{preview.words}</p>
            <ul>{preview.next.map((time) => <li key={time}>{zoneStamp(time)}</li>)}</ul>
            <p className="schedule__zone">{`Times are in ${zoneCity(zone)} time.`}</p>
          </>
        ) : null}
      </div>
    </div>
  );
}
