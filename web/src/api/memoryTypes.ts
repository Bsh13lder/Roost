// web/src/api/memoryTypes.ts — What I remember (memory plan), split out of types.ts (which re-exports it).
import type { MessageOut } from "./types";

// What I remember (memory plan): a bot's memory of you or of its work. `bot_id` null is About you.
export type MemoryKind = "about_you" | "preference" | "fact" | "project" | "lesson" | "decision";
export type MemorySource = "user" | "bot";

export interface MemoryOut {
  id: string;
  bot_id: string | null;
  kind: MemoryKind;
  text: string;
  source: MemorySource;
  importance: number;
  pinned: boolean;
  tainted: boolean;
  created_at: string;
  updated_at: string;
  last_recalled_at: string | null;
  archived_at: string | null;
}

export interface MemoryIn {
  text: string;
  kind: MemoryKind;
  bot_id?: string;
  importance?: number;
  pinned?: boolean;
}

// At least one field. `restore` brings a faded memory back.
export interface MemoryPatchIn {
  text?: string;
  kind?: MemoryKind;
  importance?: number;
  pinned?: boolean;
  restore?: true;
}

export interface MemoriesChangedFrame {
  type: "memories_changed";
  seq: number;
  change: "created" | "updated" | "deleted" | "faded";
  memory_id: string | null;
  bot_id: string | null;
}

// A memory_note message's body (JSON): the line "Remembered: ..." with Undo.
export interface MemoryNoteBody {
  memory_id: string;
  kind: MemoryKind;
  text: string;
}

// A memory_offer message's body (JSON): "Not remembered: ..." with Remember it; memory_id once you pressed it.
export interface MemoryOfferBody {
  text: string;
  kind: MemoryKind;
  memory_id: string | null;
}

// What Remember it returns: the line as it now stands and the memory it saved.
export interface RememberedOffer {
  message: MessageOut;
  memory: MemoryOut;
}
