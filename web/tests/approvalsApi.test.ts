import { afterEach, describe, expect, it, vi } from "vitest";
import { answerApproval, getApproval, listApprovals } from "../src/api/approvals";

const fetchMock = vi.fn();
afterEach(() => { fetchMock.mockReset(); vi.unstubAllGlobals(); });

function called(): { method: string; url: string; body: unknown } {
  const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
  return { method: init.method ?? "GET", url, body: init.body ? JSON.parse(init.body as string) : undefined };
}

describe("the approval api", () => {
  it("lists, gets (full or cut) and answers", async () => {
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockImplementation(async () => new Response("[]", { status: 200 }));
    await listApprovals();
    expect(called()).toMatchObject({ method: "GET", url: "/api/approvals" });
    fetchMock.mockClear();
    await getApproval("c1", true);
    expect(called()).toMatchObject({ method: "GET", url: "/api/approvals/c1?full=1" });
    fetchMock.mockClear();
    await getApproval("c1", false);
    expect(called().url).toBe("/api/approvals/c1");
    fetchMock.mockClear();
    await answerApproval("c1", "edit", "smaller");
    expect(called()).toEqual({ method: "POST", url: "/api/approvals/c1/answer", body: { answer: "edit", text: "smaller" } });
    fetchMock.mockClear();
    await answerApproval("c1", "yes");
    expect(called().body).toEqual({ answer: "yes" });
  });
});

describe("reading one card", () => {
  it("shares one request between readers of the same card while it is in flight", async () => {
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockImplementation(async () => new Response("{}", { status: 200 }));
    await Promise.all([getApproval("c2", false), getApproval("c2", false)]);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    await getApproval("c2", false);
    expect(fetchMock).toHaveBeenCalledTimes(2); // a settled read is not kept
  });
});
