import { MoneyBoard } from "../board/MoneyBoard";
import { RepeatingExpenses } from "./RepeatingExpenses";
import { TopupsCard } from "./TopupHistory";
import { UpcomingCharges } from "./UpcomingCharges";
import type { ProjectDetailBoardOut } from "../../api/projects";

export interface ProjectMoneyProps {
  project: ProjectDetailBoardOut;
  onChanged: () => void; // a top-up or a repeating charge changed: the page reloads its numbers
}

// A project's Money tab (G13): the expense line and the month's days in the main column, and in the side
// column Coming up, Repeating and Top-ups, which sit below the spending. On a phone the side goes under.
export function ProjectMoney({ project, onChanged }: ProjectMoneyProps) {
  return (
    <div className="money-grid project-money">
      <MoneyBoard project={{ id: project.id, name: project.name, currency: project.currency }} />
      <aside className="money-side" aria-label="Charges and top-ups">
        <UpcomingCharges charges={project.upcoming_charges} />
        <RepeatingExpenses rules={project.repeating} onChanged={onChanged} />
        <TopupsCard projectId={project.id} topups={project.topups} onChanged={onChanged} />
      </aside>
    </div>
  );
}
