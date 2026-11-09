import { afterEach, describe, expect, it, vi } from "vitest";
import { apiSendOnLeave } from "../src/api/client";
import { updateTaskOnLeave } from "../src/api/tasks";

// Lead 01b: a save sent as the page goes away (pagehide) must outlive the page: fetch with keepalive, and nobody waits.
afterEach(() => vi.unstubAllGlobals());

describe("requests sent on leaving the page", () => {
  it("go out with keepalive and the session, as JSON", () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);
    apiSendOnLeave("PATCH", "/api/tasks/t1", { title: "Fix it" });
    expect(fetchMock).toHaveBeenCalledWith("/api/tasks/t1", expect.objectContaining({
      method: "PATCH", keepalive: true, credentials: "include", body: JSON.stringify({ title: "Fix it" }),
      headers: { "Content-Type": "application/json" },
    }));
  });

  it("never throws, even when the request fails", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("offline")));
    expect(() => apiSendOnLeave("PATCH", "/api/tasks/t1", {})).not.toThrow();
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(warn).toHaveBeenCalled();
    warn.mockRestore();
  });

  it("a task's leave save is a PATCH of the task, its id escaped", () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);
    updateTaskOnLeave("t 1", { category: "Home" });
    expect(fetchMock).toHaveBeenCalledWith("/api/tasks/t%201", expect.objectContaining({ method: "PATCH", keepalive: true }));
  });
});
