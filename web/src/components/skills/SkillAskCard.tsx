import { useCallback, useEffect, useRef, useState } from "react";
import { Badge } from "../../ui/Badge";
import { Button } from "../../ui/Button";
import { ApiError, describeError } from "../../api/client";
import * as skillsApi from "../../api/skills";
import type { SkillProposalOut } from "../../api/skills";
import { useLiveState } from "../../hooks/useLiveStore";
import { RichText } from "../chat/RichText";
import {
  FIELD_LABELS, FROM_ROUTINE, MARK, NOT_NOW, NOT_SAVED, PROPOSAL_GONE, SAVE_SKILL, SAVED,
} from "./constants";

const TITLES = { create: "New skill", change: "Change a skill" } as const;

function NewSkill({ proposal }: { proposal: SkillProposalOut }) {
  const { name, use_when: useWhen, body } = proposal.payload;
  return (
    <>
      <p className="skill-card__name">{name}</p>
      <p className="skill-card__when">{FIELD_LABELS.use_when}: {useWhen}</p>
      <div className="skill-card__steps"><RichText text={body ?? ""} id={`skill-proposal-${proposal.id}`} /></div>
    </>
  );
}

function Change({ proposal }: { proposal: SkillProposalOut }) {
  return (
    <>
      <p className="skill-card__name">{proposal.skill_name}</p>
      <dl className="skill-card__diff">
        {proposal.diff.map((change) => (
          <div key={change.field} className="skill-card__field">
            <dt className="skill-card__label">{FIELD_LABELS[change.field]}</dt>
            <dd className="skill-card__before" aria-label="Before">{change.before}</dd>
            <dd className="skill-card__after" aria-label="After">{change.after}</dd>
          </div>
        ))}
      </dl>
    </>
  );
}

// A skill a bot offers (or a change to one), in full: the name, Use when and every step, never cut short. Only
// Save skill makes the server write it. A 409 means another press decided it: the card reloads. Text is text.
export default function SkillAskCard({ proposalId }: { proposalId: string }) {
  const version = useLiveState().skillVersion?.proposals;
  const [proposal, setProposal] = useState<SkillProposalOut | null>(null);
  const [gone, setGone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const latest = useRef(0);
  const load = useCallback(() => {
    const ticket = ++latest.current;
    skillsApi.getSkillProposal(proposalId)
      .then((loaded) => { if (ticket === latest.current) { setProposal(loaded); setGone(false); } })
      .catch((err: unknown) => {
        if (ticket !== latest.current) return;
        if (err instanceof ApiError && err.status === 404) setGone(true);
        else setError(describeError(err));
      });
  }, [proposalId]);
  useEffect(() => load(), [load, version]);

  const decide = async (call: (id: string) => Promise<SkillProposalOut>) => {
    setBusy(true);
    setError(null);
    try { setProposal(await call(proposalId)); } catch (err) {
      if (err instanceof ApiError && err.status === 409) load();
      else setError(describeError(err));
    } finally { setBusy(false); }
  };
  if (gone) return <p className="skill-card__state">{PROPOSAL_GONE}</p>;
  if (proposal === null) return error ? <p className="skill-card__error" role="alert">{error}</p> : null;
  if (proposal.state !== "open") {
    return <p className="skill-card__state">{proposal.state === "saved" ? SAVED : NOT_SAVED}</p>;
  }
  return (
    <section className="skill-card" aria-label={TITLES[proposal.action]}>
      <p className="skill-card__kicker">{TITLES[proposal.action]}</p>
      {proposal.action === "create" ? <NewSkill proposal={proposal} /> : <Change proposal={proposal} />}
      {proposal.tainted ? <Badge tone="danger">{MARK}</Badge> : null}
      {proposal.from_routine ? <Badge tone="warn">{FROM_ROUTINE}</Badge> : null}
      {error ? <p className="skill-card__error" role="alert">{error}</p> : null}
      <div className="skill-card__actions">
        <Button variant="primary" size="sm" loading={busy} onClick={() => void decide(skillsApi.saveSkillProposal)}>{SAVE_SKILL}</Button>
        <Button variant="secondary" size="sm" disabled={busy} onClick={() => void decide(skillsApi.declineSkillProposal)}>{NOT_NOW}</Button>
      </div>
    </section>
  );
}
