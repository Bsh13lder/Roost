import { beforeEach, describe, expect, it, vi } from "vitest";

const apiRequestMock = vi.fn();
vi.mock("../src/api/client", () => ({ apiRequest: (...args: unknown[]) => apiRequestMock(...args) }));
import { addMemory, forgetMemory, listMemories, updateMemory } from "../src/api/memories";

beforeEach(() => apiRequestMock.mockReset().mockResolvedValue([]));

describe("memories api", () => {
  it("lists a bot's memories and the shared ones, faded only when asked", async () => {
    await listMemories("bot 1");
    expect(apiRequestMock).toHaveBeenLastCalledWith("GET", "/api/memories?bot_id=bot%201");
    await listMemories("bot-1", { faded: true });
    expect(apiRequestMock).toHaveBeenLastCalledWith("GET", "/api/memories?bot_id=bot-1&faded=true");
  });

  it("adds, edits, pins and forgets through the memory routes", async () => {
    await addMemory({ text: "Likes tea", kind: "about_you" });
    expect(apiRequestMock).toHaveBeenLastCalledWith("POST", "/api/memories", { text: "Likes tea", kind: "about_you" });
    await updateMemory("m/1", { text: "Likes green tea" });
    expect(apiRequestMock).toHaveBeenLastCalledWith("PATCH", "/api/memories/m%2F1", { text: "Likes green tea" });
    await updateMemory("m-1", { pinned: true });
    expect(apiRequestMock).toHaveBeenLastCalledWith("PATCH", "/api/memories/m-1", { pinned: true });
    await updateMemory("m-1", { restore: true });
    expect(apiRequestMock).toHaveBeenLastCalledWith("PATCH", "/api/memories/m-1", { restore: true });
    await forgetMemory("m-1");
    expect(apiRequestMock).toHaveBeenLastCalledWith("DELETE", "/api/memories/m-1");
  });
});
