import { QuestionBook } from "./QuestionBook";

// The Question book in the bot's Settings. This file is the lazy chunk's entry, loaded when its fold opens.
export default function QuestionsSection({ botId }: { botId: string }) {
  return <QuestionBook botId={botId} />;
}
