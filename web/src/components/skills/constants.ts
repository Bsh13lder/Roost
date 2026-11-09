// Skills (web): the words and limits the Skills fold, the editor, the card and the import sheet share.
// The limits mirror roost/constants.py ("Skills"); the server checks them again and has the last word.
export const SKILL_NAME_MAX = 80;
export const SKILL_USE_WHEN_MAX = 200;
export const SKILL_BODY_MAX = 8000;

export const SKILLS_TITLE = "Skills";
export const SKILLS_EMPTY = "No skills yet. Save one here, or press Save skill when a bot offers one.";
export const NEW_SKILL = "New skill";
export const SAVE_SKILL = "Save skill";
export const NOT_NOW = "Not now";
export const ON_FOR_BOT = "On for this bot";
export const MARK = "from web content";
export const FROM_ROUTINE = "A routine proposed this";
export const DELETE_QUESTION = "Delete this skill for every bot?";
export const CONFLICT_TEXT = "This skill changed since you opened it.";
export const LOAD_LATEST = "Load the latest";
export const KEEP_MINE = "Keep mine";
export const SAVED = "Saved";
export const NOT_SAVED = "Not saved";
export const PROPOSAL_GONE = "This proposal is gone.";
export const ADD_TITLE = "Add its skills?";
export const ADD_SKILLS = "Add skills";
export const SKIP = "Skip";
export const HAVE_IT = "You already have this one";

export const FIELD_LABELS = { name: "Name", use_when: "Use when", body: "Steps" } as const;

export const onSummary = (n: number) => `${n} on`;
export const fileHasSkills = (n: number) => `This file has ${n} ${n === 1 ? "skill" : "skills"}`;
