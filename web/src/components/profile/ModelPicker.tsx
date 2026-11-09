import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { ErrorNotice } from "../ErrorNotice";
import { describeError, setBotModel } from "../../api/client";
import type { BotOut } from "../../api/types";
import { DEFAULT_EFFORT_VALUE, defaultEffortLabel, effortLabel, fetchModels, modelHint, type ModelsOut } from "../../lib/models";
import { Select } from "../../ui/Select";
import { useToast } from "../../ui/Toast";

function useModels(): { models: ModelsOut | null; error: string | null } {
  const [state, setState] = useState<{ models: ModelsOut | null; error: string | null }>({ models: null, error: null });
  useEffect(() => {
    let live = true;
    fetchModels().then((models) => { if (live) setState({ models, error: null }); })
      .catch((err: unknown) => { if (live) setState({ models: null, error: describeError(err) }); });
    return () => { live = false; };
  }, []);
  return state;
}

// The Model and Effort rows of a bot's Info. Picking either saves at once; ?try=<id> (from the new-model
// banner) opens the Model list.
export function ModelPicker({ bot, onChange }: { bot: BotOut; onChange: (bot: BotOut) => void }) {
  const { models, error: loadError } = useModels();
  const [saveError, setSaveError] = useState<string | null>(null);
  const [params] = useSearchParams();
  const toast = useToast();
  if (loadError) return <div className="info-row"><ErrorNotice message={loadError} /></div>;
  if (models === null) return null;
  const save = async (model: string, effort: BotOut["effort"]) => {
    setSaveError(null);
    try {
      const saved = await setBotModel(bot.id, model, effort);
      onChange(saved);
      toast.show(`${bot.name} now runs on ${saved.model_label}`, { tone: "ok" });
    } catch (err) {
      setSaveError(describeError(err));
    }
  };
  const options = models.choices.map((c) => ({ value: c.id, label: c.new ? `${c.label} · New` : c.label, hint: modelHint(c) }));
  const chosen = models.choices.find((c) => c.id === bot.model);
  const chosenHint = chosen ? modelHint(chosen) : undefined;
  const efforts = [
    { value: DEFAULT_EFFORT_VALUE, label: defaultEffortLabel(models, bot.model) },
    ...models.efforts.map((level) => ({ value: level as string, label: effortLabel(level) })),
  ];
  return (
    <>
      <div className="info-row">
        <div className="info-row__line">
          <span className="info-row__label">Model</span>
          <Select label="Model" size="md" value={bot.model} options={options} defaultOpen={params.get("try") !== null}
            onChange={(model) => void save(model, bot.effort)} />
        </div>
        {chosen && chosenHint ? <p className="info-row__hint">{`${chosen.label}: ${chosenHint}`}</p> : null}
      </div>
      <div className="info-row info-row--select">
        <span className="info-row__label">Effort</span>
        <Select label="Effort" size="md" value={bot.effort ?? DEFAULT_EFFORT_VALUE} options={efforts}
          onChange={(level) => void save(bot.model, level === DEFAULT_EFFORT_VALUE ? null : (level as BotOut["effort"]))} />
      </div>
      {saveError ? <div className="info-row"><ErrorNotice message={saveError} /></div> : null}
    </>
  );
}
