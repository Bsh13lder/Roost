import { useNavigate } from "react-router-dom";
import { useBotById, useMainBot } from "./useMainBot";
import { RobotFace } from "../robot/RobotFace";
import { botRole, lensbotShape } from "../robot/look";
import type { BotOut } from "../../api/types";
import { Button } from "../../ui/Button";
import { EmptyState } from "../../ui/EmptyState";

const ROBOT_PX = 72;
const MONEY_LINE = "input[aria-label='New expense']";

// The bot's own robot, in its own colours, as the empty state's picture. Without a bot: no picture.
function Art({ bot }: { bot: BotOut }) {
  return <RobotFace shape={lensbotShape(bot.avatar.shape)} role={botRole(bot.avatar.role)} color={bot.avatar.color} size={ROBOT_PX} still
    picture={bot.avatar.picture} star={bot.is_primary} />;
}

function AskButton({ bot }: { bot: BotOut }) {
  const navigate = useNavigate();
  return <Button variant="primary" onClick={() => navigate(`/bots/${encodeURIComponent(bot.id)}`)}>Ask {bot.name}</Button>;
}

// Tasks, nothing to do (G14): the main bot's robot, the first thing to try, and a button to its chat.
export function TasksEmpty() {
  const main = useMainBot();
  return (
    <EmptyState className="board-empty-state" art={main ? <Art bot={main} /> : undefined} title="Nothing here. Nice."
      hint={main ? `Add a task above, or ask ${main.name}: “plan my week”.` : "Add a task above."}
      action={main ? <AskButton bot={main} /> : undefined} />
  );
}

// A project with no tasks yet: the lead bot is named when it has one, else the main bot.
export function ProjectTasksEmpty({ leadBotId }: { leadBotId: string | null }) {
  const main = useMainBot();
  const lead = useBotById(leadBotId);
  const bot = lead ?? main;
  return (
    <EmptyState className="board-empty-state" art={bot ? <Art bot={bot} /> : undefined} title="No tasks yet"
      hint={bot ? `Add the first task, or ask ${bot.name}.` : "Add the first task."}
      action={bot ? <AskButton bot={bot} /> : undefined} />
  );
}

// A month with no spending (G14): the action focuses the expense line above.
export function MoneyEmpty() {
  const main = useMainBot();
  return (
    <EmptyState className="board-empty-state" art={main ? <Art bot={main} /> : undefined} title="Nothing spent yet this month"
      hint="Type an expense in the line above, like “€12 lunch /Trip”."
      action={<Button variant="primary" onClick={() => document.querySelector<HTMLInputElement>(MONEY_LINE)?.focus()}>Add an expense</Button>} />
  );
}
