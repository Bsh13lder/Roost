import { apiRequest } from "./client";
import type { MemoryIn, MemoryKind, MemoryOut, MemoryPatchIn } from "./types";

// What a bot remembers (memory plan, Task 10): About you and the bot's own, `faded` adds the archived ones.

const memoryPath = (memoryId: string) => `/api/memories/${encodeURIComponent(memoryId)}`;

export function listMemories(
  botId: string, { faded = false, kind }: { faded?: boolean; kind?: MemoryKind } = {},
): Promise<MemoryOut[]> {
  const fade = faded ? "&faded=true" : "";
  const only = kind ? `&kind=${encodeURIComponent(kind)}` : "";
  return apiRequest<MemoryOut[]>("GET", `/api/memories?bot_id=${encodeURIComponent(botId)}${fade}${only}`);
}

export function addMemory(input: MemoryIn): Promise<MemoryOut> {
  return apiRequest<MemoryOut>("POST", "/api/memories", input);
}

export function updateMemory(memoryId: string, patch: MemoryPatchIn): Promise<MemoryOut> {
  return apiRequest<MemoryOut>("PATCH", memoryPath(memoryId), patch);
}

export function forgetMemory(memoryId: string): Promise<void> {
  return apiRequest<void>("DELETE", memoryPath(memoryId));
}
