import { Badge } from "../../ui/Badge";

// A small mark on a task or expense that the LazyClaw import made. The server says so (`imported_from`);
// nothing is written into the user's own text.
export function FromLazyClawMark({ from }: { from?: string | null }) {
  if (from !== "lazyclaw") return null;
  return <Badge className="from-lazyclaw">from LazyClaw</Badge>;
}
