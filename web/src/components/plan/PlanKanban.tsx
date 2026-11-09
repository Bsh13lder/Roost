import { useCallback, useState } from "react";
import { MoreIcon } from "../icons";
import { Menu, MenuItem, MenuNote } from "../../ui/Menu";
import { Switch } from "../../ui/Switch";
import { cx } from "../../ui/cx";
import type { PlanItemOut, PlanStatus } from "../../api/plan";
import { useKanbanDrag } from "../board/kanban/useKanbanDrag";
import { PlanItemMeta } from "./PlanItemBits";
import { PLAN_COLUMNS, itemsIn, visibleColumns } from "./planColumns";

export interface PlanKanbanProps {
  items: readonly PlanItemOut[];
  onMove: (itemId: string, status: PlanStatus) => void;
}

// The Plan as columns (Planned · On it · Done, Dropped behind a toggle). It reuses the Board's drag hook and its
// column and card looks. A card drags between columns; its menu has Move to… for keyboards and touch.
export function PlanKanban({ items, onMove }: PlanKanbanProps) {
  const [showDropped, setShowDropped] = useState(false);
  const drag = useKanbanDrag(useCallback((id: string, key: string) => onMove(id, key as PlanStatus), [onMove]));
  const columns = visibleColumns(showDropped);
  return (
    <div className="plan-kanban">
      <Switch checked={showDropped} onChange={setShowDropped}>Show dropped</Switch>
      <div className="kboard plan-kboard" role="group" aria-label="Plan Kanban">
        {columns.map((one) => {
          const cards = itemsIn(items, one.key);
          const drop = drag.columnProps(one);
          return (
            <section key={one.key} className={cx("kcol", drop.isOver && "is-over")} aria-label={one.label} data-column={one.key}
              onDragOver={drop.onDragOver} onDragLeave={drop.onDragLeave} onDrop={drop.onDrop}>
              <div className="kcol__head">
                <span className="kcol__name">{one.label}</span>
                <span className="count" aria-label={`${cards.length} ${cards.length === 1 ? "item" : "items"}`}>{cards.length}</span>
              </div>
              {cards.map((card) => (
                <PlanCard key={card.id ?? `line-${card.line_no}`} item={card} dragging={drag.dragging === card.id}
                  dragProps={card.id ? drag.cardProps(card.id) : undefined} onMove={onMove} />
              ))}
              {cards.length === 0 ? <div className="kcol__empty">Drop a card here</div> : null}
            </section>
          );
        })}
      </div>
    </div>
  );
}

interface PlanCardProps {
  item: PlanItemOut;
  dragging: boolean;
  dragProps: ReturnType<ReturnType<typeof useKanbanDrag>["cardProps"]> | undefined;
  onMove: PlanKanbanProps["onMove"];
}

function PlanCard({ item, dragging, dragProps, onMove }: PlanCardProps) {
  const id = item.id;
  return (
    <div className={cx("kcard", item.status === "done" && "is-done", dragging && "is-dragging")} {...dragProps}>
      <div className="kcard__t">
        <span className="t">{item.text}</span>
        {id ? (
          <Menu label={`More for ${item.text}`} trigger={<MoreIcon />}>
            <MenuNote>Move to…</MenuNote>
            {PLAN_COLUMNS.filter((one) => one.key !== item.status).map((one) => (
              <MenuItem key={one.key} onSelect={() => onMove(id, one.key as PlanStatus)}>{one.label}</MenuItem>
            ))}
          </Menu>
        ) : null}
      </div>
      <div className="kcard__meta">
        {item.date ? <span className="kcard__due">{item.date}</span> : null}
        <PlanItemMeta item={item} />
      </div>
    </div>
  );
}
