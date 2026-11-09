// "Update my instructions?" (replies track): a bot offers new instructions for itself. The card shows why and every
// changed line; only Accept (as offered, or after Edit) makes the server write them. A 409 means another press
// decided it: the card reloads. A lazy chunk, like the skill and routine cards. Text is text.
import { useCallback, useEffect, useRef, useState } from "react";
import { Badge } from "../../ui/Badge";
import { Button } from "../../ui/Button";
import { Textarea } from "../../ui/Textarea";
import { ApiError, describeError } from "../../api/client";
import * as api from "../../api/instructions";
import type { InstructionDiffLine, InstructionProposalOut } from "../../api/instructions";
import { useLiveState } from "../../hooks/useLiveStore";

const TITLE = "Update my instructions?";
const STATE_TEXT = { accepted: "Instructions updated", declined: "Instructions kept" } as const;
const GONE = "This card is gone.";
const STALE = "You changed this bot's instructions since this card was made, so it can't be accepted.";
const MAX = 4000; // roost/constants.py MAX_BOT_INSTRUCTIONS_LENGTH

function DiffLine({ line }: { line: InstructionDiffLine }) {
  if (line.op === "same") return <div className="instructions-card__same">{line.text || " "}</div>;
  const cls = line.op === "add" ? "skill-card__after" : "skill-card__before";
  return <div className={cls} aria-label={line.op === "add" ? "Added" : "Removed"}>{line.text || " "}</div>;
}

function useProposal(proposalId: string) {
  const version = useLiveState().instructionVersion;
  const [proposal, setProposal] = useState<InstructionProposalOut | null>(null);
  const [gone, setGone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const latest = useRef(0);
  const load = useCallback(() => {
    const ticket = ++latest.current;
    api.getInstructionProposal(proposalId)
      .then((loaded) => { if (ticket === latest.current) { setProposal(loaded); setGone(false); } })
      .catch((err: unknown) => {
        if (ticket !== latest.current) return;
        if (err instanceof ApiError && err.status === 404) setGone(true);
        else setError(describeError(err));
      });
  }, [proposalId]);
  useEffect(() => load(), [load, version]);
  return { proposal, setProposal, gone, error, setError, load };
}

export default function InstructionsAskCard({ proposalId }: { proposalId: string }) {
  const { proposal, setProposal, gone, error, setError, load } = useProposal(proposalId);
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState<string | null>(null); // Edit: your version of the new instructions

  const decide = async (call: () => Promise<InstructionProposalOut>) => {
    setBusy(true);
    setError(null);
    try { setProposal(await call()); setDraft(null); } catch (err) {
      if (err instanceof ApiError && err.status === 409) load();
      else setError(describeError(err));
    } finally { setBusy(false); }
  };
  if (gone) return <p className="skill-card__state">{GONE}</p>;
  if (proposal === null) return error ? <p className="skill-card__error" role="alert">{error}</p> : null;
  if (proposal.state !== "open") return <p className="skill-card__state">{STATE_TEXT[proposal.state]}</p>;
  const accept = () => decide(() => api.acceptInstructionProposal(proposalId, draft ?? undefined));
  return (
    <section className="skill-card" aria-label={TITLE}>
      <p className="skill-card__kicker">{TITLE}</p>
      {proposal.why ? <p className="instructions-card__why">{proposal.why}</p> : null}
      {draft === null ? (
        <div className="instructions-card__diff">
          {proposal.diff.map((line, i) => <DiffLine key={i} line={line} />)}
        </div>
      ) : (
        <Textarea className="instructions-card__edit" aria-label="Your version" value={draft} maxLength={MAX}
          autoGrow={false} onChange={(event) => setDraft(event.target.value)} />
      )}
      {proposal.tainted ? <Badge tone="danger">from web content</Badge> : null}
      {proposal.from_routine ? <Badge tone="warn">A routine proposed this</Badge> : null}
      {proposal.stale ? <p className="skill-card__error">{STALE}</p> : null}
      {error ? <p className="skill-card__error" role="alert">{error}</p> : null}
      <div className="skill-card__actions">
        <Button variant="primary" size="sm" loading={busy} disabled={proposal.stale || draft === ""}
          onClick={() => void accept()}>Accept</Button>
        {draft === null ? (
          <Button variant="secondary" size="sm" disabled={busy} onClick={() => setDraft(proposal.after)}>Edit</Button>
        ) : null}
        <Button variant="secondary" size="sm" disabled={busy}
          onClick={() => void decide(() => api.declineInstructionProposal(proposalId))}>Decline</Button>
      </div>
    </section>
  );
}
