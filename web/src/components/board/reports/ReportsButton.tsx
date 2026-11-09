import { lazy, Suspense, useState } from "react";
import type { BoardProjectTotalOut } from "../../../api/money";
import { Button } from "../../../ui/Button";
import { Sheet } from "../../../ui/Sheet";

// The full reports, with their chart, are their own chunk: the Money tab's entry carries neither.
const MoneyReports = lazy(() => import("./MoneyReports"));

export interface ReportsButtonProps {
  rows: readonly BoardProjectTotalOut[]; // the shown month's by_project
  monthLabel: string;
  projectId?: string;
}

// Reports, beside Export CSV: the months' trend per currency (6 or 12) and the month by project, in a sheet. Nothing
// is asked for until it opens.
export function ReportsButton({ rows, monthLabel, projectId }: ReportsButtonProps) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button variant="ghost" size="md" className="money-wide-only" onClick={() => setOpen(true)}>Reports</Button>
      <Sheet open={open} onOpenChange={setOpen} title="Reports">
        {open ? (
          <Suspense fallback={<p className="board-loading">Loading&hellip;</p>}>
            <MoneyReports rows={rows} monthLabel={monthLabel} projectId={projectId} />
          </Suspense>
        ) : null}
      </Sheet>
    </>
  );
}
