import { Suspense, lazy, useState } from "react";
import { useNavigate } from "react-router-dom";
import { BotForm, newBotValues, type BotFormValues } from "../components/BotForm";
import { ErrorNotice } from "../components/ErrorNotice";
import { useLiveState } from "../hooks/useLiveStore";
import { useTemplates } from "../hooks/useTemplates";
import * as botsApi from "../api/bots";
import * as templatesApi from "../api/templates";
import { describeError } from "../api/client";
import type { TemplateFormOut, TemplateOut, TemplateSkillCheck } from "../api/types";
import { fileHasSkills } from "../components/skills/constants";
import { announceTeamChanged } from "../lib/teamChanged";

const toValues = (source: TemplateFormOut | TemplateOut, templateId: string | null): BotFormValues => ({
  name: source.name, job: source.job, instructions: source.instructions,
  avatar: { ...source.avatar, badge: "none" }, template_id: templateId,
});

// Skills: after Create from a file, the Add its skills? sheet (a lazy chunk).
const TemplateSkillsSheet = lazy(() => import("../components/skills/TemplateSkillsSheet"));

const NOT_JSON = "That file is not a Roost bot file (it is not JSON).";
// A bot file is name, job, up to 4,000 characters of instructions, a look and up to 20 skills: far under this.
const MAX_FILE_BYTES = 256 * 1024;

function readText(file: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(reader.error ?? new Error("unreadable"));
    reader.readAsText(file);
  });
}

// "Start from" (S1.7): a template or a checked file only fills the form; Create makes the bot.
function StartFrom({ templates, onFill, onFile }: {
  templates: TemplateOut[]; onFill: (values: BotFormValues) => void; onFile: (file: File) => void;
}) {
  return (
    <div className="presets" role="group" aria-label="Start from">
      <span className="presets__label">Start from</span>
      {templates.map((t) => (
        <button key={t.id} type="button" className="btn btn--quiet btn--small" onClick={() => onFill(toValues(t, t.id))}>{t.label}</button>
      ))}
      <label className="btn btn--quiet btn--small presets__file">
        From a file
        <input type="file" accept=".json,application/json" className="sr-only"
          onChange={(e) => { const chosen = e.target.files?.[0]; e.target.value = ""; if (chosen) onFile(chosen); }} />
      </label>
    </div>
  );
}

// The file's skills, each readable in full before Create; nothing is added until the sheet after Create.
function FileSkills({ skills }: { skills: readonly TemplateSkillCheck[] }) {
  return (
    <section className="template-skills" aria-label="Skills in this file">
      <p className="template-skills__title">{fileHasSkills(skills.length)}</p>
      <ul className="template-skills__list">
        {skills.map((skill, index) => (
          <li key={`${skill.name}-${index}`} className="template-skill">
            <details>
              <summary>{skill.name}</summary>
              <p className="template-skill__when">{skill.use_when}</p>
              <pre className="template-skill__steps">{skill.body}</pre>
            </details>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function NewBot() {
  const navigate = useNavigate();
  const { templates, error: templatesError } = useTemplates();
  const usedColors = Object.values(useLiveState().bots).map((bot) => bot.avatar.color);
  const [initial, setInitial] = useState<BotFormValues | undefined>(undefined);
  const [formKey, setFormKey] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [fileSkills, setFileSkills] = useState<readonly TemplateSkillCheck[]>([]);
  const [made, setMade] = useState<string | null>(null); // the new bot, while its file's skills are offered
  const fill = (values: BotFormValues, skills: readonly TemplateSkillCheck[] = []) => {
    setError(null); setInitial(values); setFormKey((key) => key + 1); setFileSkills(skills);
  };
  const fromFile = async (file: File) => {
    setError(null);
    if (file.size > MAX_FILE_BYTES) {
      setError("That file is too big to be a Roost bot file.");
      return;
    }
    let parsed: unknown;
    try {
      parsed = JSON.parse(await readText(file));
    } catch {
      setError(NOT_JSON);
      return;
    }
    try {
      const checked = await templatesApi.checkTemplateFile(parsed); // the server checks it; nothing is created
      fill(toValues(checked, null), checked.skills ?? []);
    } catch (err) {
      setError(describeError(err));
    }
  };
  const submit = async (values: BotFormValues) => {
    setError(null);
    try {
      const bot = await botsApi.createBot({ ...values, avatar: { ...values.avatar, badge: "none" } });
      announceTeamChanged();
      if (fileSkills.length > 0) setMade(bot.id);
      else navigate(`/bots/${bot.id}`);
    } catch (err) {
      setError(describeError(err)); // the form stays filled in
    }
  };
  return (
    <div className="page new-bot-page">
      <header className="page__header">
        <h1 className="page__title">New bot</h1>
        <p className="page__lede">Give it a name, a job, instructions and a look. It gets its own computer and every tool.</p>
      </header>
      <StartFrom templates={templates} onFill={fill} onFile={(file) => void fromFile(file)} />
      {templatesError ? <ErrorNotice message={`Templates could not be loaded: ${templatesError}`} /> : null}
      {error ? <ErrorNotice message={error} /> : null}
      {fileSkills.length > 0 ? <FileSkills skills={fileSkills} /> : null}
      <BotForm key={formKey} initial={initial ?? newBotValues(usedColors)} submitLabel="Create bot"
        onSubmit={(values) => void submit(values)} />
      {made ? (
        <Suspense fallback={null}>
          <TemplateSkillsSheet botId={made} skills={fileSkills} onDone={() => navigate(`/bots/${made}`)} />
        </Suspense>
      ) : null}
    </div>
  );
}
