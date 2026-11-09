import { afterEach, describe, expect, it, vi } from "vitest";
import { adoptAccountZone } from "../src/lib/accountZone";
import { putTimeZone } from "../src/api/timeZone";
import { appTimeZone, browserTimeZone, setAppTimeZone } from "../src/lib/timeZone";

afterEach(() => { setAppTimeZone("Europe/Madrid"); vi.restoreAllMocks(); });

describe("putTimeZone", () => {
  afterEach(() => { vi.unstubAllGlobals(); });

  it("saves the zone with PUT /api/auth/timezone", async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ timezone: "Asia/Tokyo" }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await expect(putTimeZone("Asia/Tokyo")).resolves.toEqual({ timezone: "Asia/Tokyo" });
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/auth/timezone");
    expect(init.method).toBe("PUT");
    expect(JSON.parse(String(init.body))).toEqual({ timezone: "Asia/Tokyo" });
  });

  it("refuses with the server's words on a 422", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ detail: "Not a time zone." }), { status: 422 })));
    await expect(putTimeZone("Mars/Olympus")).rejects.toThrow("Not a time zone.");
  });
});

describe("adoptAccountZone", () => {
  it("saves the device's zone silently when the account has none", async () => {
    const put = vi.fn().mockResolvedValue({ timezone: browserTimeZone() });
    setAppTimeZone("Asia/Tokyo");
    await adoptAccountZone(null, put);
    expect(put).toHaveBeenCalledWith(browserTimeZone());
    expect(appTimeZone()).toBe(browserTimeZone());
  });

  it("uses the account's zone and saves nothing when it is set", async () => {
    const put = vi.fn();
    await adoptAccountZone("America/New_York", put);
    expect(put).not.toHaveBeenCalled();
    expect(appTimeZone()).toBe("America/New_York");
  });

  it("does nothing when the server did not say", async () => {
    const put = vi.fn();
    await adoptAccountZone(undefined, put);
    expect(put).not.toHaveBeenCalled();
    expect(appTimeZone()).toBe("Europe/Madrid");
  });

  it("keeps the device's zone when saving fails, and says why in the console", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const put = vi.fn().mockRejectedValue(new Error("offline"));
    await adoptAccountZone(null, put);
    expect(appTimeZone()).toBe(browserTimeZone());
    expect(warn).toHaveBeenCalled();
  });

  it("ignores a stored zone this browser does not know", async () => {
    const put = vi.fn();
    await adoptAccountZone("Mars/Olympus", put);
    expect(appTimeZone()).toBe("Europe/Madrid");
    expect(put).not.toHaveBeenCalled();
  });
});
