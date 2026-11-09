// The models a bot can run on (GET /api/models) and the words for them. One fetch is shared by every
// picker and the banner; a failed fetch is forgotten so the next call tries again.
import { apiRequest } from "../api/client";
import type { BotOut } from "../api/types";

export type EffortLevel = NonNullable<BotOut["effort"]>;

export interface ModelChoiceOut {
  id: string;
  label: string;
  line: string; // "fable" | "sonnet" | "opus" | "haiku", or "new" for one the daily check found
  new: boolean;
}

export interface ModelsOut {
  choices: ModelChoiceOut[];
  efforts: EffortLevel[];
  default_model: string;
  default_effort: Readonly<Record<string, string>>;
  notice: { id: string; label: string } | null;
}

export const DEFAULT_EFFORT_VALUE = "default"; // a Select value is never ""

// A short hint for each model a bot can run on, by its family line (roost/llm/registry.py BOT_MODELS).
export const MODEL_HINTS: Readonly<Record<string, string>> = {
  fable: "the most capable",
  sonnet: "balanced, the usual choice",
  opus: "careful, deep work",
  haiku: "fast and cheap",
};

export const modelHint = (choice: ModelChoiceOut): string | undefined => MODEL_HINTS[choice.line];

let cached: Promise<ModelsOut> | null = null;

export function fetchModels(): Promise<ModelsOut> {
  if (cached === null) {
    const request = apiRequest<ModelsOut>("GET", "/api/models");
    cached = request;
    request.catch(() => { if (cached === request) cached = null; });
  }
  return cached;
}

export function resetModelsCache(): void {
  cached = null;
}

export function dismissModelNotice(modelId: string): Promise<void> {
  return apiRequest<void>("POST", `/api/models/notice/${encodeURIComponent(modelId)}/dismiss`);
}

export function effortLabel(effort: string | null): string {
  return effort ? effort.charAt(0).toUpperCase() + effort.slice(1) : "Default";
}

export function defaultEffortLabel(models: ModelsOut, modelId: string): string {
  const level = models.default_effort[modelId];
  return level ? `Default (${level})` : "Default";
}

// A model Ask card's body (message kind "model_suggestion"): JSON the gateway wrote from a model's
// arguments, so every field is checked.
export interface ModelSuggestionData {
  bot_id: string;
  bot: string;
  model: string;
  label: string;
  effort: EffortLevel | null;
  reason: string;
}

const EFFORT_LEVELS: readonly string[] = ["low", "medium", "high", "max"];

export function parseModelSuggestion(body: string): ModelSuggestionData | null {
  try {
    const d = JSON.parse(body);
    const texts = [d?.bot_id, d?.bot, d?.model, d?.label, d?.reason].every((v) => typeof v === "string");
    const effortOk = d?.effort == null || EFFORT_LEVELS.includes(d.effort);
    if (!texts || !effortOk) return null;
    return { bot_id: d.bot_id, bot: d.bot, model: d.model, label: d.label, effort: d.effort ?? null, reason: d.reason };
  } catch {
    return null;
  }
}
