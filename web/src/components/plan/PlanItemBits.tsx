import { Badge } from "../../ui/Badge";
import type { PlanItemOut } from "../../api/plan";

// What follows an item's text everywhere in the Plan: its time, tags and the "from web content" mark. Item text is
// always drawn as React text.
export function PlanItemMeta({ item }: { item: PlanItemOut }) {
  return (
    <>
      {item.time ? <span className="plan-item__time">{item.time}</span> : null}
      {item.tags.map((tag) => <span key={tag} className="plan-item__tag">#{tag}</span>)}
      {item.tainted ? <Badge tone="danger" className="plan-item__taint">from web content</Badge> : null}
    </>
  );
}
