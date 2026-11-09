import { Badge } from "../../ui/Badge";
import type { ApprovalStepOut } from "../../api/types";
import { ArgRows } from "./ArgRows";
import { StepCrop } from "./CropView";
import { DiffView } from "./DiffView";
import { HARD_FLOOR_BADGE, OUTSIDE_CONTENT_MARK } from "./constants";

export interface StepRowProps {
  cardId: string;
  index: number;
  step: ApprovalStepOut;
  numbered?: boolean; // a Proposal numbers its steps
}

// One step of a card: what it will do, any hard-floor badge, a screen act's picture of the button, the red outside-content line and its diff.
export function StepRow({ cardId, index, step, numbered = false }: StepRowProps) {
  return (
    <li className="step-row">
      <div className="step-row__head">
        {numbered ? <span className="step-row__n">{index + 1}.</span> : null}
        <span className="step-row__title">{step.title}</span>
        {step.floor ? <Badge tone="warn">{HARD_FLOOR_BADGE}</Badge> : null}
      </div>
      <StepCrop cardId={cardId} index={index} step={step} />
      <ArgRows cardId={cardId} stepIndex={index} rows={step.rows} />
      {step.detail ? <p className="step-row__detail">{step.detail}</p> : null}
      {step.tainted_basis ? <p className="step-row__outside">{OUTSIDE_CONTENT_MARK}</p> : null}
      {step.diff ? <DiffView cardId={cardId} stepIndex={index} diff={step.diff} /> : null}
    </li>
  );
}
