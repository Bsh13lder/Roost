import { Suspense, lazy, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { MemoryPanel } from "../memory/MemoryPanel";
import { ComputerKindSwitch } from "../computer/ComputerKindSwitch";
import { ErrorNotice } from "../ErrorNotice";
import { DecisionsCard } from "./DecisionsCard";
import { ModelPicker } from "./ModelPicker";
import { ApprovalModeCard } from "./ApprovalModeCard";
import { FoldersCard } from "./FoldersCard";
import { FullLimitSwitch } from "./FullLimitSwitch";
import { VoiceSection, voiceSummary } from "./VoiceSection";
import { useVoiceInfo } from "../../lib/voiceInfo";
import { FOLDERS_TITLE, MODE_OPTIONS } from "../approvals/constants";
import { Button } from "../../ui/Button";
import { Fold } from "../../ui/Fold";
import { useSkillsOn } from "../skills/useSkillsOn";
import { onSummary, SKILLS_TITLE } from "../skills/constants";
import { ChevronIcon, ShareIcon } from "../icons";
import { describeError } from "../../api/client";
import type { BotOut } from "../../api/types";
import { RETIRE_LABEL, RETIRE_MAIN_HINT, useRetireBot } from "../../hooks/useRetireBot";

// Skills: the list, the switches and the editor are a lazy chunk, loaded when the fold opens.
const SkillsSection = lazy(() => import("../skills/SkillsSection"));
// The Bot Journal (obsidian track): its own chunk, loaded when the fold opens.
const JournalSection = lazy(() => import("../journal/JournalSection"));
// Connectors: the list and the editor (the key is write-only) are a lazy chunk, loaded when the fold opens.
const ConnectorsSection = lazy(() => import("../connectors/ConnectorsSection"));
// The Question book: its own chunk, loaded when the fold opens.
const QuestionsSection = lazy(() => import("../questions/QuestionsSection"));
// Token usage: its own chunk, loaded when the fold opens.
const UsageSection = lazy(() => import("../usage/UsageSection"));

const firstLine = (text: string) => text.split("\n").find((line) => line.trim())?.trim() ?? "";
const modeLabel = (bot: BotOut) => MODE_OPTIONS.find((option) => option.id === bot.approval.mode)?.label;
const loading = (what: string) => <p className="skills__loading">Loading {what}&hellip;</p>;

// One group of settings: a quiet heading over a rounded card.
function Group({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="settings-group" aria-label={title}>
      <h3 className="settings-group__title">{title}</h3>
      <div className="profile-card settings-group__card">{children}</div>
    </section>
  );
}

// Voice (voice plan V3): how the bot sounds when a reply is read aloud; the voice's name shows while it is folded.
function VoiceFold({ bot, onChange }: Pick<SettingsPageProps, "bot" | "onChange">) {
  const info = useVoiceInfo();
  return (
    <Fold id="voice" title="Voice" summary={voiceSummary(info.status === "ready" ? info.info : null, bot.voice)}>
      <VoiceSection bot={bot} onChange={onChange} />
    </Fold>
  );
}

function ModelGroup({ bot, onChange, onShare }: SettingsPageProps) {
  return (
    <Group title="Model & effort">
      <Link to={`/bots/${bot.id}/instructions`} className="info-row info-row--link">
        <span className="info-row__label">Instructions</span>
        <span className="info-row__value">{firstLine(bot.instructions) || "Add instructions"}</span>
        <ChevronIcon />
      </Link>
      <ModelPicker bot={bot} onChange={onChange} />
      <VoiceFold bot={bot} onChange={onChange} />
      <Fold id="usage" title="Usage">
        <Suspense fallback={loading("the usage")}><UsageSection botId={bot.id} /></Suspense>
      </Fold>
      <button type="button" className="info-row info-row--link" onClick={onShare}>
        <span className="info-row__label">Share as Template</span>
        <span className="info-row__value">Save a file</span>
        <ShareIcon />
      </button>
    </Group>
  );
}

function KnowsGroup({ bot }: { bot: BotOut }) {
  const skillsOn = useSkillsOn(bot.id);
  return (
    <Group title="What it knows">
      <Fold id="memory" title="What I remember"><MemoryPanel bot={bot} /></Fold>
      <Fold id="skills" title={SKILLS_TITLE} summary={skillsOn === null ? undefined : onSummary(skillsOn)}>
        <Suspense fallback={loading("skills")}><SkillsSection botId={bot.id} /></Suspense>
      </Fold>
      <Fold id="decisions" title="Decisions"><DecisionsCard botId={bot.id} /></Fold>
      <Fold id="questions" title="Question book">
        <Suspense fallback={loading("questions")}><QuestionsSection botId={bot.id} /></Suspense>
      </Fold>
      <Fold id="journal" title="Journal">
        <Suspense fallback={loading("the journal")}><JournalSection botId={bot.id} /></Suspense>
      </Fold>
    </Group>
  );
}

function ComputerGroup({ bot, onChange }: Pick<SettingsPageProps, "bot" | "onChange">) {
  return (
    <Group title="Computer and your Mac">
      <ComputerKindSwitch bot={bot} onChange={onChange} />
      <Fold id="folders" title={FOLDERS_TITLE}><FoldersCard bot={bot} /></Fold>
      <Fold id="connectors" title="Connectors">
        <Suspense fallback={loading("connectors")}><ConnectorsSection botId={bot.id} /></Suspense>
      </Fold>
      <FullLimitSwitch bot={bot} onChange={onChange} />
    </Group>
  );
}

// Retire this bot, at the very end, in the danger style. The main bot can't be retired: the star moves first.
function RetireCard({ bot }: { bot: BotOut }) {
  const retire = useRetireBot(bot);
  const [error, setError] = useState<string | null>(null);
  const run = () => {
    setError(null);
    retire().catch((err: unknown) => setError(describeError(err)));
  };
  return (
    <section className="settings-group settings-group--danger" aria-label={RETIRE_LABEL}>
      {bot.is_primary ? <p className="settings-group__hint">{RETIRE_MAIN_HINT}</p> : null}
      {error ? <ErrorNotice message={error} /> : null}
      <Button variant="danger" block disabled={bot.is_primary} onClick={run}>{RETIRE_LABEL}</Button>
    </section>
  );
}

export interface SettingsPageProps { bot: BotOut; onChange: (bot: BotOut) => void; onShare: () => void }

// The bot's Settings page (restructure slice 3): everything that was on Info, in grouped cards. The heavier sections
// fold away, closed until you open them, and this browser remembers.
export function SettingsPage({ bot, onChange, onShare }: SettingsPageProps) {
  return (
    <div className="settings-page">
      <ModelGroup bot={bot} onChange={onChange} onShare={onShare} />
      <section className="settings-group" aria-label="Approvals">
        <h3 className="settings-group__title">Approvals{modeLabel(bot) ? ` · ${modeLabel(bot)}` : ""}</h3>
        <ApprovalModeCard bot={bot} onChange={onChange} />
      </section>
      <KnowsGroup bot={bot} />
      <ComputerGroup bot={bot} onChange={onChange} />
      <RetireCard bot={bot} />
    </div>
  );
}
