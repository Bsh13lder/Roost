import { Chip } from "../../../ui/Chip";

export interface NoProjectChipProps {
  count: number;
  more: boolean; // there are more than the first page: "100+"
  open: boolean; // the inbox is in the main column
  onToggle: () => void;
}

// "No project · 3" on the expense list's tools row: a filter chip that swaps the list for the inbox of expenses with
// no project (GET /api/money/general), where each can be given one, and back. Nothing waiting: no chip.
export function NoProjectChip({ count, more, open, onToggle }: NoProjectChipProps) {
  if (count === 0 && !open) return null;
  return <Chip className="money-wide-only" selected={open} onClick={onToggle}>No project · {count}{more ? "+" : ""}</Chip>;
}
