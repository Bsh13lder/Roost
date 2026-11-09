import { useCallback, useEffect, useId, useRef, useState } from "react";
import { Button } from "../../ui/Button";
import { Input } from "../../ui/Input";
import { Select } from "../../ui/Select";
import { DatePicker } from "../../ui/date/DatePicker";
import { addDays, todayIn } from "../../ui/date/dates";
import type { QuickPick } from "../../ui/date/picks";
import { resolveDay } from "../../ui/date/resolve";
import { describeError } from "../../api/client";
import * as standingApi from "../../api/standing";
import type { PermissionOut, StandingAction } from "../../api/standing";
import { ErrorNotice } from "../ErrorNotice";
import {
  STANDING_ACTIONS, STANDING_DEFAULT_DAYS, STANDING_MAX_PER_DAY, STANDING_UNTIL_MAX_DAYS, permissionWords,
} from "./standingWords";

const UNTIL_PICKS: readonly QuickPick[] = [
  { label: "In a week", day: (today) => addDays(today, STANDING_DEFAULT_DAYS) },
  { label: "In two weeks", day: (today) => addDays(today, STANDING_DEFAULT_DAYS * 2) },
  { label: `In ${STANDING_UNTIL_MAX_DAYS} days`, day: (today) => addDays(today, STANDING_UNTIL_MAX_DAYS) },
];

interface Draft { action: StandingAction; host: string; count: string; until: string }

const emptyDraft = (): Draft => ({ action: "post", host: "", count: "1", until: addDays(todayIn(), STANDING_DEFAULT_DAYS) });

function PermissionLine({ permission, onRevoke }: { permission: PermissionOut; onRevoke: () => Promise<void> }) {
  const [busy, setBusy] = useState(false);
  const revoke = async () => { setBusy(true); try { await onRevoke(); } finally { setBusy(false); } };
  return (
    <li className="standing__item">
      <span className="standing__words">{permissionWords(permission)}</span>
      <span className="standing__used">{`Used ${permission.used_today} today`}</span>
      <Button size="sm" variant="ghost" loading={busy} onClick={() => void revoke()}>Revoke</Button>
    </li>
  );
}

// "Standing permission" for one routine (Step 2): what it may post, send or submit on one site with nobody
// watching, as the owner's own sentence, with Revoke (at once). Fable still checks every act it covers.
export function StandingPermissions({ routineId }: { routineId: string }) {
  const headId = useId();
  const [permissions, setPermissions] = useState<readonly PermissionOut[] | null>(null);
  const [draft, setDraft] = useState<Draft>(emptyDraft);
  const [error, setError] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const latest = useRef(0);
  const load = useCallback(() => {
    const ticket = ++latest.current;
    standingApi.listPermissions(routineId)
      .then((found) => { if (ticket === latest.current) { setPermissions(found); setLoadError(null); } })
      .catch((err: unknown) => { if (ticket === latest.current) setLoadError(describeError(err)); });
  }, [routineId]);
  useEffect(() => load(), [load]);

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      const until = (await resolveDay(draft.until)) ?? "";
      const made = await standingApi.addPermission(routineId, {
        host: draft.host.trim(), action: draft.action, max_per_day: Number(draft.count), until });
      setPermissions((now) => [...(now ?? []).filter((p) => p.host !== made.host || p.action !== made.action), made]);
      setDraft(emptyDraft());
    } catch (err) {
      setError(describeError(err));
    } finally {
      setSaving(false);
    }
  };
  const revoke = async (permission: PermissionOut) => {
    setError(null);
    try {
      await standingApi.revokePermission(routineId, permission.id);
      setPermissions((now) => (now ?? []).filter((p) => p.id !== permission.id));
    } catch (err) {
      setError(describeError(err));
    }
  };
  const set = (patch: Partial<Draft>) => setDraft((now) => ({ ...now, ...patch }));
  return (
    <section className="standing" aria-labelledby={headId}>
      <h4 className="standing__title" id={headId}>Standing permission</h4>
      <p className="standing__hint">What this routine may do with nobody watching. Fable checks each act, and anything else asks you.</p>
      {loadError ? <ErrorNotice message={loadError} onRetry={load} /> : null}
      {permissions?.length === 0 ? <p className="standing__empty">None. Everything it posts, sends or submits asks you first.</p> : null}
      <ul className="standing__list">
        {(permissions ?? []).map((p) => <PermissionLine key={p.id} permission={p} onRevoke={() => revoke(p)} />)}
      </ul>
      <div className="standing__row" role="group" aria-label="New standing permission">
        <span>Let it</span>
        <Select size="sm" label="Action" value={draft.action} options={STANDING_ACTIONS} onChange={(action) => set({ action })} />
        <span>on</span>
        <Input controlSize="sm" className="standing__host" aria-label="Site" placeholder="x.com" value={draft.host}
          onChange={(event) => set({ host: event.target.value })} />
        <span>up to</span>
        <Input controlSize="sm" className="standing__count" aria-label="A day" type="number" min={1} max={STANDING_MAX_PER_DAY}
          value={draft.count} onChange={(event) => set({ count: event.target.value })} />
        <span>a day until</span>
        <DatePicker label="Until" value={draft.until} picks={UNTIL_PICKS} onChange={(until) => set({ until })} />
        <Button size="sm" variant="secondary" loading={saving} onClick={() => void save()}>Save permission</Button>
      </div>
      {error ? <p className="standing__error" role="alert">{error}</p> : null}
    </section>
  );
}
