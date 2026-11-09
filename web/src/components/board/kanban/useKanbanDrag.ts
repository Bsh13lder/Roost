import { useCallback, useMemo, useRef, useState, type DragEvent } from "react";
import type { KanbanColumn } from "./kanbanGroups";

const CARD_TYPE = "text/plain";

export interface CardDrag {
  draggable: true;
  onDragStart: (event: DragEvent<HTMLElement>) => void;
  onDragEnd: () => void;
}

export interface ColumnDrop {
  onDragOver: (event: DragEvent<HTMLElement>) => void;
  onDragLeave: (event: DragEvent<HTMLElement>) => void;
  onDrop: (event: DragEvent<HTMLElement>) => void;
  isOver: boolean;
}

export interface KanbanDrag {
  dragging: string | null; // the card being dragged
  cardProps: (taskId: string) => CardDrag;
  columnProps: (column: KanbanColumn, lane?: string) => ColumnDrop;
}

const spot = (column: KanbanColumn, lane: string | undefined) => `${lane ?? ""}|${column.key}`;

// Native HTML5 drag between columns (G6, no library). A drop reports the card's id, the column and the row
// (`lane`) it landed in. A column that is not a drop target (Overdue, the Bot columns) never cancels dragover,
// so the browser shows the not-allowed cursor and a drop there does nothing. Touch screens do not drag: they
// use Move to… in the card's menu.
export function useKanbanDrag(onDrop: (taskId: string, key: string, lane: string | undefined) => void): KanbanDrag {
  const [dragging, setDragging] = useState<string | null>(null);
  const [over, setOver] = useState<string | null>(null);
  const current = useRef<string | null>(null);

  const end = useCallback(() => { current.current = null; setDragging(null); setOver(null); }, []);
  const cardProps = useCallback((taskId: string): CardDrag => ({
    draggable: true,
    onDragStart: (event) => {
      current.current = taskId;
      event.dataTransfer?.setData(CARD_TYPE, taskId);
      if (event.dataTransfer) event.dataTransfer.effectAllowed = "move";
      setDragging(taskId);
    },
    onDragEnd: end,
  }), [end]);

  const columnProps = useCallback((column: KanbanColumn, lane?: string): ColumnDrop => ({
    isOver: over === spot(column, lane),
    onDragOver: (event) => {
      if (!column.dropTarget || current.current === null) return;
      event.preventDefault();
      if (event.dataTransfer) event.dataTransfer.dropEffect = "move";
      setOver(spot(column, lane));
    },
    onDragLeave: (event) => {
      if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setOver((now) => (now === spot(column, lane) ? null : now));
    },
    onDrop: (event) => {
      if (!column.dropTarget) return;
      event.preventDefault();
      const id = current.current ?? event.dataTransfer?.getData(CARD_TYPE) ?? "";
      end();
      if (id) onDrop(id, column.key, lane);
    },
  }), [end, onDrop, over]);

  return useMemo(() => ({ dragging, cardProps, columnProps }), [dragging, cardProps, columnProps]);
}
