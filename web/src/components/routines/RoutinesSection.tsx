import { RoutinesCard } from "./RoutinesCard";

// The routines under the bot's Plan (restructure slice 3): a switch each, tap to edit, + New routine. This file is
// the lazy chunk's entry, so none of it is in the main bundle.
export default function RoutinesSection({ botId }: { botId: string }) {
  return <RoutinesCard botId={botId} />;
}
