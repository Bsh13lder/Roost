import { useEffect, useState } from "react";
import { getApproval } from "../../api/approvals";
import { describeError } from "../../api/client";
import type { ApprovalStepOut } from "../../api/types";
import { CROP_FAILED, CU_ACT_TOOLS } from "./constants";

// Plain base64 only: anything else never reaches the data address.
const BASE64 = /^[A-Za-z0-9+/]+={0,2}$/;

// The button's words, from the card's title ("Click 'Buy now'" → "Buy now"); the whole title when it quotes none.
export function buttonLabel(title: string): string {
  const quoted = /'(.+)'/.exec(title);
  return quoted ? quoted[1] : title;
}

// C3: the picture of the button the bot wants to press, as the server cut it from the page.
export function CropView({ crop, label }: { crop: string; label: string }) {
  if (!BASE64.test(crop)) return null;
  return <img className="crop-view" src={`data:image/jpeg;base64,${crop}`} alt={`The button: ${label}`} />;
}

// A screen act's picture, fetched once from the full card (live frames and lists never carry it). A failed fetch
// says so in one quiet line; the card still works with its words.
export function StepCrop({ cardId, index, step }: { cardId: string; index: number; step: ApprovalStepOut }) {
  const act = CU_ACT_TOOLS.has(step.tool);
  const [crop, setCrop] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!act) return undefined;
    let cancelled = false;
    getApproval(cardId, true)
      .then((card) => { if (!cancelled) setCrop(card.steps[index]?.crop ?? null); })
      .catch((err: unknown) => {
        if (cancelled) return;
        console.warn("approval crop", describeError(err));
        setError(CROP_FAILED);
      });
    return () => { cancelled = true; };
  }, [act, cardId, index]);
  if (error) return <p className="crop-view__failed">{error}</p>;
  return crop ? <CropView crop={crop} label={buttonLabel(step.title)} /> : null;
}
