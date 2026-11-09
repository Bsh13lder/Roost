import { useState } from "react";
import { Badge } from "../../ui/Badge";
import { Button } from "../../ui/Button";
import { Switch } from "../../ui/Switch";
import { describeError } from "../../api/client";
import * as proposalsApi from "../../api/proposals";
import type { ProposalOut } from "../../api/proposals";
import { useOpenProposals } from "../../hooks/useOpenProposals";
import { zoneStamp } from "../routines/zoneTime";
import { permissionWords } from "../routines/standingWords";

const NEXT_SHOWN = 3;
const MARK_OUTSIDE = "This run read outside content.";
const MARK_ROUTINE = "A routine asked to change a routine.";
const FIELD_LABEL = { name: "Name", instructions: "What to do", schedule: "Schedule", watch: "Runs when" } as const;
const TITLES = { create: "New routine", change: "Change a routine", pause: "Pause a routine" } as const;

function Fields({ proposal }: { proposal: ProposalOut }) {
  const payload = proposal.payload;
  if (proposal.action === "pause") return <p className="routine-ask__name">{proposal.routine_name ?? "This routine"}</p>;
  if (proposal.action === "change") {
    return (
      <dl className="routine-ask__diff">
        <dt className="routine-ask__name">{proposal.routine_name}</dt><dd />
        {proposal.diff.map((change) => (
          <div key={change.field} className="routine-ask__change">
            <dt>{FIELD_LABEL[change.field]}</dt>
            <dd className="routine-ask__before">{change.before}</dd>
            <dd className="routine-ask__after">{change.after}</dd>
          </div>
        ))}
      </dl>
    );
  }
  return (
    <>
      <p className="routine-ask__name">{payload?.name}</p>
      <p className="routine-ask__words">{proposal.words}</p>
      <ul className="routine-ask__next" aria-label="Next runs">
        {proposal.next.slice(0, NEXT_SHOWN).map((time) => <li key={time}>{zoneStamp(time)}</li>)}
      </ul>
      <p className="routine-ask__instructions">{payload?.instructions}</p>
    </>
  );
}

// A standing permission the bot proposed with a new routine: on by default; switched off, Approve stores none.
function ProposedPermission({ proposal, keep, onKeep }: { proposal: ProposalOut; keep: boolean; onKeep: (on: boolean) => void }) {
  const permission = proposal.action === "create" ? proposal.payload?.permission : null;
  if (!permission) return null;
  return (
    <div className="routine-ask__permission">
      <Switch checked={keep} onChange={onKeep}>{`Also: ${permissionWords(permission)}`}</Switch>
      <p className="standing__hint">Fable checks each act it covers, and you can revoke it in the routine.</p>
    </div>
  );
}

function Settled({ state }: { state: ProposalOut["state"] | null }) {
  const word = state === "approved" ? "Approved" : state === "declined" ? "Declined" : state === "expired" ? "Expired" : "Already decided";
  return <p className="routine-ask routine-ask--settled">{word}</p>;
}

// A routine a bot wants (or a change, or a pause), shown in full so you can decide: every field the server will
// write, the next three runs on the account's clock, and what was read. Approve is what makes the server write it. Text is
// always drawn as text.
export function RoutineAskCard({ proposalId }: { proposalId: string }) {
  const { proposals } = useOpenProposals();
  const [decided, setDecided] = useState<ProposalOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [keep, setKeep] = useState(true);
  const open = proposals?.find((one) => one.id === proposalId) ?? null;
  const approve = (id: string) => (keep ? proposalsApi.approveProposal(id) : proposalsApi.approveProposal(id, { permission: null }));
  const decide = async (call: (id: string) => Promise<ProposalOut>) => {
    setBusy(true);
    setError(null);
    try { setDecided(await call(proposalId)); } catch (err) { setError(describeError(err)); } finally { setBusy(false); }
  };
  if (decided) return <Settled state={decided.state} />;
  if (proposals === null) return null;
  if (!open) return <Settled state={null} />;
  return (
    <section className="routine-ask" aria-label={TITLES[open.action]}>
      <h4 className="routine-ask__title">{TITLES[open.action]}</h4>
      <Fields proposal={open} />
      <ProposedPermission proposal={open} keep={keep} onKeep={setKeep} />
      {open.from_routine ? <Badge tone="danger">{MARK_ROUTINE}</Badge> : null}
      {open.tainted ? <Badge tone="danger">{MARK_OUTSIDE}</Badge> : null}
      {error ? <p className="routine-ask__error" role="alert">{error}</p> : null}
      <div className="routine-ask__buttons">
        <Button variant="primary" size="sm" loading={busy} onClick={() => void decide(approve)}>Approve</Button>
        <Button variant="secondary" size="sm" disabled={busy} onClick={() => void decide(proposalsApi.declineProposal)}>Decline</Button>
      </div>
    </section>
  );
}
