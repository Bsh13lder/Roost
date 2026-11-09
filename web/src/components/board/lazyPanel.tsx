import { Suspense, type ComponentType, type LazyExoticComponent } from "react";

// What a lazy Board panel may be told: the project it is narrowed to (a project page), or nothing (the Board).
export interface PanelProps {
  projectId?: string;
  openId?: string | null; // an item to open now (a project page's "New note" line made it)
}

// Heavier panels are their own chunks (M2 D4), so the main bundle stays small. This shows the Board's
// loading line while a chunk arrives, and passes the panel its props.
export function lazyPanel(Panel: LazyExoticComponent<ComponentType<PanelProps>>) {
  return function LazyPanel(props: PanelProps) {
    return (
      <Suspense fallback={<p className="board-loading">Loading&hellip;</p>}>
        <Panel {...props} />
      </Suspense>
    );
  };
}
