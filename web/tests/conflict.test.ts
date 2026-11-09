import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiRequest } from "../src/api/client";
import { RevisionConflictError, withConflict } from "../src/api/conflict";

afterEach(() => vi.unstubAllGlobals());

describe("errors that carry the stored copy (M2 D4)", () => {
  it("keeps the error body on ApiError", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ detail: "changed", current: { id: "n1" } }),
      { status: 409, headers: { "Content-Type": "application/json" } })));
    await expect(apiRequest("PUT", "/api/notes/n1", {})).rejects.toMatchObject({
      status: 409, message: "changed", body: { current: { id: "n1" } },
    });
  });

  it("turns a 409 that carries the current copy into a RevisionConflictError", async () => {
    const failing = Promise.reject(new ApiError(409, "changed", { detail: "changed", current: { id: "n1", revision: 3 } }));
    const caught = await withConflict(failing).catch((err: unknown) => err);
    expect(caught).toBeInstanceOf(RevisionConflictError);
    expect((caught as RevisionConflictError<{ revision: number }>).current.revision).toBe(3);
  });

  it("passes any other error, and a success, through", async () => {
    await expect(withConflict(Promise.reject(new ApiError(404, "Note not found")))).rejects.toBeInstanceOf(ApiError);
    await expect(withConflict(Promise.resolve(1))).resolves.toBe(1);
  });
});
