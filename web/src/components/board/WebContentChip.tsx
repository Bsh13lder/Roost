// "from web content": a bot wrote this after reading a page, so every bot that
// lists it is treated as having read outside content. Keep is the user vouching
// for it — the mark goes (only the user can do this; no bot can).
export interface WebContentChipProps {
  what: string; // names the row for the button's label: "Buy milk", "the food expense"
  onKeep?: () => void; // without it the mark stands alone (a day note: nothing to keep)
}

export function WebContentChip({ what, onKeep }: WebContentChipProps) {
  return (
    <>
      <span className="board-chip board-chip--web">from web content</span>
      {onKeep ? <button type="button" className="board-keep" aria-label={`Keep ${what} as yours`}
        title="You checked it: mark it as yours, not web content" onClick={onKeep}>
        Keep
      </button> : null}
    </>
  );
}
