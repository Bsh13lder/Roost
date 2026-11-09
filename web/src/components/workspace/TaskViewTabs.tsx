import { MAIN_VIEWS, MORE_VIEWS, type BoardView } from "../board/constants";
import { ChevronDownIcon } from "../icons";
import { Menu, MenuItem } from "../../ui/Menu";
import { cx } from "../../ui/cx";

export interface ViewCounts {
  today: number | null; // overdue plus due today
  inbox: number | null; // open tasks with no project
  upcoming: number | null;
}

export interface TaskViewTabsProps {
  view: BoardView;
  onView: (view: BoardView) => void;
  counts: ViewCounts;
}

const LABEL: Record<BoardView, string> = {
  today: "Today", inbox: "Inbox", upcoming: "Upcoming", someday: "Someday", overdue: "Overdue", done: "Done",
};
const isMore = (view: BoardView) => (MORE_VIEWS as readonly BoardView[]).includes(view);

// The Workspace's Tasks tabs (app restructure): Today · Inbox · Upcoming with the server's counts, and Someday,
// Overdue and Done behind More (its button names the one picked from it).
export function TaskViewTabs({ view, onView, counts }: TaskViewTabsProps) {
  return (
    <div className="ws-views" role="group" aria-label="Task views">
      {MAIN_VIEWS.map((id) => {
        const count = counts[id];
        return (
          <button key={id} type="button" className={cx("ws-view", view === id && "is-current")} aria-pressed={view === id}
            onClick={() => onView(id)}>
            {LABEL[id]}{count ? <span className="count">{count}</span> : null}
          </button>
        );
      })}
      <span className={cx("ws-views__more", isMore(view) && "is-current")}>
        <Menu label="More views" align="start" trigger={<>{isMore(view) ? LABEL[view] : "More"}<ChevronDownIcon /></>}>
          {MORE_VIEWS.map((id) => <MenuItem key={id} onSelect={() => onView(id)}>{LABEL[id]}</MenuItem>)}
        </Menu>
      </span>
    </div>
  );
}
