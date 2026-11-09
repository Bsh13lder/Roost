import { useMemo, useState } from "react";
import { describeError } from "../../api/client";
import { putTimeZone } from "../../api/timeZone";
import { browserTimeZone, setAppTimeZone, supportedTimeZones, useAppTimeZone, zoneCity } from "../../lib/timeZone";
import { Group } from "./SettingsGroups";

export const TIME_ZONE_TITLE = "Time zone";

// "New York (America/New_York)": a zone in the list, its city first.
const optionLabel = (zone: string): string => (zone.includes("/") ? `${zoneCity(zone)} (${zone})` : zone);

// Settings → Time zone (owner, 2026-11-09): the account's zone by its city, a list of every zone, and this
// device's zone one tap away when they differ. A change is saved first; only then do the times follow it
// (the open page is drawn again on the new clock).
export function TimeZoneGroup() {
  const zone = useAppTimeZone();
  const device = browserTimeZone();
  const zones = useMemo(() => supportedTimeZones([zone, device]), [zone, device]);
  const [saving, setSaving] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  const choose = async (next: string) => {
    if (next === zone || saving) return;
    setSaving(true);
    setProblem(null);
    try {
      const saved = await putTimeZone(next);
      setAppTimeZone(saved.timezone || next);
    } catch (err: unknown) {
      console.warn("Roost could not save the time zone.", err);
      setProblem(describeError(err));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Group title={TIME_ZONE_TITLE}>
      <div className="settings-sheet__field">
        <span className="settings-sheet__label">{zoneCity(zone)}</span>
        <select className="input settings-sheet__zone" aria-label={TIME_ZONE_TITLE} value={zone} disabled={saving}
          onChange={(event) => void choose(event.target.value)}>
          {zones.map((name) => <option key={name} value={name}>{optionLabel(name)}</option>)}
        </select>
        {zone !== device ? (
          <button type="button" className="btn btn--secondary btn--sm" disabled={saving}
            onClick={() => void choose(device)}>{`Use this device's (${zoneCity(device)})`}</button>
        ) : null}
        {problem ? <p className="settings-sheet__note" role="alert">{problem}</p> : null}
        <p className="settings-sheet__note">Every date and time in Roost is shown on this clock.</p>
      </div>
    </Group>
  );
}
