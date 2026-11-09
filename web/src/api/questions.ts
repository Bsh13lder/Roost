// web/src/api/questions.ts — the question book: what a bot wondered and the default it carried on with.
import { apiRequest } from "./client";

export interface QuestionOut {
  id: string;
  bot_id: string;
  routine_id: string | null;
  question: string;
  default_choice: string;
  why: string | null;
  answer: string | null;
  tainted: boolean;
  state: "open" | "answered" | "dismissed";
  created_at: string;
  answered_at: string | null;
}

const path = (id: string) => `/api/questions/${encodeURIComponent(id)}`;

// A bot's open questions, or every bot's when `botId` is left out (My turn).
export const listQuestions = (botId?: string) =>
  apiRequest<{ questions: QuestionOut[] }>("GET", `/api/questions?state=open${botId ? `&bot_id=${encodeURIComponent(botId)}` : ""}`)
    .then((r) => r.questions);
export const answerQuestion = (id: string, answer: string) => apiRequest<QuestionOut>("POST", `${path(id)}/answer`, { answer });
export const dismissQuestion = (id: string) => apiRequest<QuestionOut>("POST", `${path(id)}/dismiss`);
