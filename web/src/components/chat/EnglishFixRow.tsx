import type { EnglishFix, EnglishFixBody, MessageOut } from "../../api/types";
import { fixSegments, parseEnglishFix, type FixSegment, type FixShown } from "../../lib/englishFix";

export const YOU_SAID_LABEL = "You said:";
const ARROW = " → ";

function Segment({ segment }: { segment: FixSegment }) {
  if (segment.kind === "wrong") return <del className="english-fix__wrong">{segment.text}</del>;
  if (segment.kind === "right") return <ins className="english-fix__right">{segment.text}</ins>;
  return <>{segment.text}</>;
}

// A fix that could not be placed in the sentence: wrong → right, after it.
function Trail({ fix }: { fix: EnglishFix }) {
  return (
    <span className="english-fix__trail">
      <del className="english-fix__wrong">{fix.wrong}</del>
      {ARROW}
      <ins className="english-fix__right">{fix.right}</ins>
    </span>
  );
}

// The corrected sentence with its fixes inline, then what you said. Shared by the chat's card and the call screen's
// caption (where it takes the place of the plain words you said).
export function EnglishFixText({ fix }: { fix: FixShown }) {
  const shown = fixSegments(fix);
  return (
    <>
      <p className="english-fix__sentence">
        {shown.segments.map((segment, index) => <Segment key={index} segment={segment} />)}
        {shown.trailing.map((trail, index) => <Trail key={`trail-${index}`} fix={trail} />)}
      </p>
      <p className="english-fix__said">{`${YOU_SAID_LABEL} ${fix.said}`}</p>
    </>
  );
}

export const FIX_ROW_LABEL = "What you said, corrected";

// Correct what I say: a quiet card under the spoken message of yours it corrects (lib/englishFix.ts places it);
// a body that is not an english_fix draws nothing.
export function EnglishFixRow({ message }: { message: MessageOut }) {
  const fix = parseEnglishFix(message.body);
  if (!fix) return null;
  return (
    <li className="message message--english-fix" data-message-id={message.id} aria-label={FIX_ROW_LABEL}>
      <div className="english-fix">
        <EnglishFixText fix={fix} />
      </div>
    </li>
  );
}
