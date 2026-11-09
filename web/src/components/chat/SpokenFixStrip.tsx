import type { SpokenCorrection } from "../../hooks/useMicRecorder";
import { Button } from "../../ui/Button";
import { EnglishFixText } from "./EnglishFixRow";

export const FIX_STRIP_LABEL = "Corrected what you said";
export const KEEP_MY_WORDS_LABEL = "Keep my words";

// Correct what I say (voice tuning D3): above the composer, the cleaned sentence with each fix marked (the wrong
// words struck through, the right words beside them) and what you said, so you check before you send; Keep my
// words puts the raw transcript back.
export function SpokenFixStrip({ correction, onKeep }: { correction: SpokenCorrection; onKeep: () => void }) {
  return (
    <div className="composer__fix english-fix" role="status" aria-label={FIX_STRIP_LABEL}>
      <EnglishFixText fix={correction} />
      <Button size="sm" variant="ghost" className="composer__fix-keep" onClick={onKeep}>{KEEP_MY_WORDS_LABEL}</Button>
    </div>
  );
}
