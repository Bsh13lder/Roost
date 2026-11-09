import { useState } from "react";
import { REACTION_GLYPHS, REACTION_KEYS, type ReactionKey } from "./constants";

// The tapback under a message: its glyph, named for screen readers.
export function ReactionChip({ reaction }: { reaction: ReactionKey }) {
  const { glyph, label } = REACTION_GLYPHS[reaction];
  return <span className="message__reaction" role="img" aria-label={`Reaction: ${label}`}>{glyph}</span>;
}

// A small picker beside Copy: one button opens the five tapbacks; the one already chosen clears when pressed again.
export function ReactionPicker({ current, onReact }: { current?: ReactionKey; onReact: (key: ReactionKey | null) => void }) {
  const [open, setOpen] = useState(false);
  const pick = (key: ReactionKey) => { setOpen(false); onReact(key === current ? null : key); };
  return (
    <span className="message__react">
      <button type="button" className="message__react-open" aria-label="React" aria-expanded={open} onClick={() => setOpen(!open)}>☺</button>
      {open ? REACTION_KEYS.map((key) => (
        <button key={key} type="button" className="message__react-key" aria-label={REACTION_GLYPHS[key].label}
          aria-pressed={key === current} onClick={() => pick(key)}>{REACTION_GLYPHS[key].glyph}</button>
      )) : null}
    </span>
  );
}
