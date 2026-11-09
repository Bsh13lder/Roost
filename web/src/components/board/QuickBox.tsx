import type { ReactNode } from "react";

export interface QuickBoxProps {
  glyph: "+" | "€"; // what is being added: a task, or an expense
  label: string; // names the box for a screen reader
  children: ReactNode; // the input (and its button)
  chips?: ReactNode; // the reading of the line, under it
  help?: ReactNode; // the "?" button
}

// The frame around a quick line (G4): a panel with a glyph, the input, the "?" help and the chips under it.
// Its border takes the accent while anything inside has focus. The tasks and money tabs share it.
export function QuickBox({ glyph, label, children, chips, help }: QuickBoxProps) {
  return (
    <div className="quick-box" role="group" aria-label={label}>
      <div className="quick-box__row">
        <span className="quick-box__glyph" aria-hidden="true">{glyph}</span>
        <div className="quick-box__field">{children}</div>
        {help}
      </div>
      {chips ? <div className="quick-box__chips">{chips}</div> : null}
    </div>
  );
}
