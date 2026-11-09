import { useRef, type KeyboardEvent } from "react";

export interface SegmentedProps<T extends string> {
  label: string; // names the group
  options: ReadonlyArray<{ id: T; label: string }>;
  value: T;
  onChange: (id: T) => void;
}

// A short row of exclusive choices, such as List · Kanban · Calendar (Board redesign G4): aria-pressed buttons in a
// labelled group. Arrow keys move to the next or previous option and choose it, wrapping round.
export function Segmented<T extends string>({ label, options, value, onChange }: SegmentedProps<T>) {
  const buttons = useRef(new Map<T, HTMLButtonElement>());
  const move = (event: KeyboardEvent, from: number) => {
    const step = event.key === "ArrowRight" || event.key === "ArrowDown" ? 1
      : event.key === "ArrowLeft" || event.key === "ArrowUp" ? -1 : 0;
    if (step === 0) return;
    event.preventDefault();
    const next = options[(from + step + options.length) % options.length];
    onChange(next.id);
    buttons.current.get(next.id)?.focus();
  };
  return (
    <div className="seg" role="group" aria-label={label}>
      {options.map((option, index) => (
        <button key={option.id} type="button" aria-pressed={option.id === value}
          ref={(node) => { if (node) buttons.current.set(option.id, node); else buttons.current.delete(option.id); }}
          onClick={() => onChange(option.id)} onKeyDown={(event) => move(event, index)}>
          {option.label}
        </button>
      ))}
    </div>
  );
}
