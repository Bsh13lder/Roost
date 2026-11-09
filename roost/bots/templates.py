"""Bot templates (S1.7). A template only fills the New bot form: name, job,
instructions and look. It grants nothing, because every bot gets every tool
(S1 D2). "chief" is also what ensure_main_bot creates (S1 D4)."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping

from roost.bots.look import avatar_dict
from roost.bots.models import Avatar


@dataclass(frozen=True)
class BotTemplate:
    id: str
    label: str
    name: str
    job: str
    instructions: str
    avatar: Avatar


CHIEF = BotTemplate(
    id="chief", label="Main bot", name="Chief",
    job="Leads your team: sends each request to the right bot and brings the answers together",
    instructions=(
        "You lead this team. For each request, answer it yourself or hand parts to teammates with ask_bot, "
        "at the same time when the parts are independent, then give one short combined answer, naming a teammate only "
        "when it matters. Never claim a teammate did something its answer does not show."
    ),
    avatar=Avatar(shape="classic", color="#8b5cf6", badge="none", screen="glow"),
)
LIFE_ADMIN = BotTemplate(
    id="life_admin", label="Life admin", name="Life admin", job="Keeps your tasks, reminders and money in order",
    instructions=("Keep the user's tasks, reminders and money in order. Add a task or log an expense as soon as "
                  "the user mentions one, and say what you saved in a few words."),
    avatar=Avatar(shape="soft", color="#14b8a6", badge="none", screen="pixel"),
)
RESEARCHER = BotTemplate(
    id="researcher", label="Researcher", name="Researcher", job="Reads the web for you and reports back",
    instructions=("Read the web for the user. Open the pages you need, answer first and short, and link the "
                  "page a key fact or price came from."),
    avatar=Avatar(shape="monitor", color="#3b82f6", badge="none", screen="signal"),
)

TEMPLATES: Mapping[str, BotTemplate] = MappingProxyType({t.id: t for t in (CHIEF, LIFE_ADMIN, RESEARCHER)})


def get_template(template_id: str) -> BotTemplate | None:
    return TEMPLATES.get(template_id)


def template_out(template: BotTemplate) -> dict[str, Any]:
    return {"id": template.id, "label": template.label, "name": template.name, "job": template.job,
            "instructions": template.instructions, "avatar": avatar_dict(template.avatar)}
