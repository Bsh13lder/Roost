import { afterEach, describe, expect, it, vi } from "vitest";
import { addGrant, listGrants, pickFolder, revokeGrant, undoActivity, updateGrant } from "../src/api/mac";
import { setApproval } from "../src/api/bots";

const fetchMock = vi.fn();
afterEach(() => { fetchMock.mockReset(); vi.unstubAllGlobals(); });

function called(): { method: string; url: string; body: unknown } {
  const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
  return { method: init.method ?? "GET", url, body: init.body ? JSON.parse(init.body as string) : undefined };
}

function reply(body: unknown, status = 200) {
  vi.stubGlobal("fetch", fetchMock);
  fetchMock.mockImplementation(async () => new Response(status === 204 ? null : JSON.stringify(body), { status }));
}

describe("the Mac and approval api", () => {
  it("setApproval PUTs the mode and topics", async () => {
    reply({});
    await setApproval("b1", "plan", ["files", "tasks"]);
    expect(called()).toEqual({ method: "PUT", url: "/api/bots/b1/approval", body: { mode: "plan", ask_topics: ["files", "tasks"] } });
  });

  it("setApproval sends auto_review only when it is given", async () => {
    reply({});
    await setApproval("b1", "ask", [], true);
    expect(called().body).toEqual({ mode: "ask", ask_topics: [], auto_review: true });
  });

  it("listGrants asks for one bot's, or all", async () => {
    reply([]);
    await listGrants("b 1");
    expect(called()).toMatchObject({ method: "GET", url: "/api/mac/grants?bot_id=b%201" });
    fetchMock.mockClear();
    await listGrants();
    expect(called()).toMatchObject({ method: "GET", url: "/api/mac/grants" });
  });

  it("addGrant POSTs the body", async () => {
    reply({ id: "g1" }, 201);
    const body = { path: "/Users/me/Docs", label: "Docs", access: "read" as const, read_policy: "ask_each" as const, bot_id: null };
    await addGrant(body);
    expect(called()).toEqual({ method: "POST", url: "/api/mac/grants", body });
  });

  it("updateGrant PATCHes, revokeGrant DELETEs, pickFolder POSTs {}", async () => {
    reply({ id: "g1" });
    await updateGrant("g1", { label: "New" });
    expect(called()).toEqual({ method: "PATCH", url: "/api/mac/grants/g1", body: { label: "New" } });
    fetchMock.mockClear();
    reply(null, 204);
    await revokeGrant("g1");
    expect(called()).toMatchObject({ method: "DELETE", url: "/api/mac/grants/g1" });
    fetchMock.mockClear();
    reply({ path: null });
    expect(await pickFolder()).toEqual({ path: null });
    expect(called()).toEqual({ method: "POST", url: "/api/mac/pick-folder", body: {} });
  });

  it("undoActivity POSTs to the line's undo route", async () => {
    reply({ message: { id: "m2" } });
    await undoActivity("m1");
    expect(called()).toEqual({ method: "POST", url: "/api/mac/activity/m1/undo", body: {} });
  });
});
