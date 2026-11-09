import { useEffect, useRef, useState, type FormEvent, type RefObject } from "react";
import { ErrorNotice } from "./ErrorNotice";
import { Field } from "../ui/Field";
import { Select } from "../ui/Select";
import * as roomsApi from "../api/rooms";
import { describeError } from "../api/client";
import { orderTeam } from "../lib/team";
import type { BotOut, RoomOut } from "../api/types";

// D-E / D-G: a room holds 2–6 bots (roost/constants.py ROOM_MIN_MEMBERS,
// ROOM_MAX_MEMBERS, MAX_ROOM_NAME_LENGTH); an off-duty bot can't join;
// the coordinator defaults to the main bot (or the first bot picked).
const ROOM_MIN = 2;
const ROOM_MAX = 6;
const ROOM_NAME_MAX = 40;
const FOCUSABLE = "button:not(:disabled), input:not(:disabled), [href], [tabindex]:not([tabindex='-1'])";

export interface NewRoomDialogProps {
  bots: readonly BotOut[];
  onClose: () => void;
  onCreated: (room: RoomOut) => void;
}

// Keeps Tab inside the dialog (it is modal) and wraps at either end.
function trapTab(event: KeyboardEvent, dialog: HTMLElement | null) {
  const items = dialog ? Array.from(dialog.querySelectorAll<HTMLElement>(FOCUSABLE)) : [];
  if (items.length === 0) return;
  const first = items[0];
  const last = items[items.length - 1];
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
}

// Focus the name field on open, Escape closes, Tab stays inside, and
// focus goes back to whatever opened the dialog when it closes. An Escape
// that an open list inside already used (the Coordinator select) is its own.
function useModal(dialogRef: RefObject<HTMLDivElement | null>, firstRef: RefObject<HTMLInputElement | null>, onClose: () => void) {
  useEffect(() => {
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    firstRef.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !event.defaultPrevented) onClose();
      else if (event.key === "Tab") trapTab(event, dialogRef.current);
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      if (opener?.isConnected) opener.focus();
    };
  }, [dialogRef, firstRef, onClose]);
}

function RoomPicker({ team, picked, onToggle }: { team: BotOut[]; picked: readonly string[]; onToggle: (id: string) => void }) {
  const onDuty = team.filter((bot) => !bot.off_duty).length;
  return (
    <fieldset className="field room-pick-list">
      <legend className="field__label">Bots ({ROOM_MIN} to {ROOM_MAX})</legend>
      {team.map((bot) => {
        const checked = picked.includes(bot.id);
        return (
          <label key={bot.id} className="room-pick">
            <input
              type="checkbox"
              checked={checked}
              disabled={bot.off_duty || (!checked && picked.length >= ROOM_MAX)}
              onChange={() => onToggle(bot.id)}
            />
            <span className="room-pick__name">{bot.name}</span>
            {bot.off_duty ? <span className="room-pick__note">Off duty</span> : null}
          </label>
        );
      })}
      {onDuty < ROOM_MIN ? <p className="room-pick__hint">A room needs at least two bots on duty.</p> : null}
    </fieldset>
  );
}

function CoordinatorField({ members, value, onChange }: { members: BotOut[]; value: string | null; onChange: (id: string) => void }) {
  return (
    <Field label="Coordinator" hint="Answers any post that mentions nobody.">
      <Select value={value ?? ""} disabled={members.length === 0} placeholder="Pick the bots first"
        options={members.map((bot) => ({ value: bot.id, label: bot.name }))} onChange={onChange} />
    </Field>
  );
}

// The draft room: who is picked, and the coordinator — the one chosen if
// still picked, else the main bot, else the first bot picked.
function useRoomDraft(bots: readonly BotOut[]) {
  const team = orderTeam(bots);
  const [name, setName] = useState("");
  const [picked, setPicked] = useState<readonly string[]>([]);
  const [chosen, setChosen] = useState<string | null>(null);
  const members = team.filter((bot) => picked.includes(bot.id));
  const fallback = members.find((bot) => bot.is_primary) ?? members[0];
  const coordinator = chosen && picked.includes(chosen) ? chosen : fallback?.id ?? null;
  const valid = name.trim().length > 0 && members.length >= ROOM_MIN && members.length <= ROOM_MAX;
  const toggle = (id: string) => setPicked((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  const draft = { name: name.trim(), member_ids: members.map((bot) => bot.id), coordinator_id: coordinator };
  return { team, name, setName, picked, toggle, members, coordinator, setChosen, valid, draft };
}

export function NewRoomDialog({ bots, onClose, onCreated }: NewRoomDialogProps) {
  const room = useRoomDraft(bots);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const dialogRef = useRef<HTMLDivElement>(null);
  const nameRef = useRef<HTMLInputElement>(null);
  useModal(dialogRef, nameRef, onClose);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!room.valid || saving) return;
    setSaving(true);
    setError(null);
    try {
      onCreated(await roomsApi.createRoom(room.draft));
    } catch (err) {
      setError(describeError(err));
    } finally {
      setSaving(false);
    }
  };

  return (
    // mousedown on the backdrop itself, so a drag that ends outside the card never closes it.
    <div className="dialog-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <div ref={dialogRef} className="dialog" role="dialog" aria-modal="true" aria-labelledby="new-room-title">
        <form onSubmit={(event) => void submit(event)}>
          <h2 id="new-room-title" className="dialog__title">New room</h2>
          <label className="field">
            <span className="field__label">Room name</span>
            <input ref={nameRef} className="input" value={room.name} maxLength={ROOM_NAME_MAX} onChange={(event) => room.setName(event.target.value)} />
          </label>
          <RoomPicker team={room.team} picked={room.picked} onToggle={room.toggle} />
          <CoordinatorField members={room.members} value={room.coordinator} onChange={room.setChosen} />
          {error ? <ErrorNotice message={error} /> : null}
          <div className="dialog__actions">
            <button type="button" className="btn btn--quiet" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn btn--primary" disabled={!room.valid || saving}>Create room</button>
          </div>
        </form>
      </div>
    </div>
  );
}
