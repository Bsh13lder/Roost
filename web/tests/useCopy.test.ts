import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, renderHook } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useCopy } from "../src/hooks/useCopy";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

// A reset time no other code uses, so the timer spy finds only this hook's timers.
const RESET_MS = 4321;

function deferred(): { promise: Promise<void>; resolve: () => void; reject: (error: unknown) => void } {
  let resolve!: () => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<void>((done, fail) => { resolve = done; reject = fail; });
  return { promise, resolve, reject };
}

const flush = () => act(async () => { await Promise.resolve(); });
const resetTimers = (spy: { mock: { calls: unknown[][] } }) => spy.mock.calls.filter(([, ms]) => ms === RESET_MS);

// Review fix: a copy that settles after its code block is gone sets no state and starts no timer.
describe("useCopy after unmount", () => {
  it("does nothing when the copy succeeds after its component is gone", async () => {
    userEvent.setup(); // the clipboard stub
    const write = deferred();
    vi.spyOn(navigator.clipboard, "writeText").mockReturnValue(write.promise);
    const setTimer = vi.spyOn(window, "setTimeout");
    const { result, unmount } = renderHook(() => useCopy(RESET_MS));
    act(() => result.current.copy("npm run build"));
    unmount();
    write.resolve();
    await flush();
    expect(resetTimers(setTimer)).toEqual([]);
  });

  it("still logs a refusal that arrives after its component is gone, and starts no timer", async () => {
    userEvent.setup();
    const write = deferred();
    vi.spyOn(navigator.clipboard, "writeText").mockReturnValue(write.promise);
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    const setTimer = vi.spyOn(window, "setTimeout");
    const { result, unmount } = renderHook(() => useCopy(RESET_MS));
    act(() => result.current.copy("npm run build"));
    unmount();
    write.reject(new DOMException("Denied", "NotAllowedError"));
    await flush();
    expect(warn).toHaveBeenCalled();
    expect(resetTimers(setTimer)).toEqual([]);
  });

  it("clears a running reset timer when its component goes", async () => {
    userEvent.setup();
    const setTimer = vi.spyOn(window, "setTimeout");
    const clearTimer = vi.spyOn(window, "clearTimeout");
    const { result, unmount } = renderHook(() => useCopy(RESET_MS));
    act(() => result.current.copy("npm run build"));
    await flush();
    expect(result.current.state).toBe("copied");
    const timer = setTimer.mock.results[setTimer.mock.calls.indexOf(resetTimers(setTimer)[0])].value;
    unmount();
    expect(clearTimer).toHaveBeenCalledWith(timer);
  });
});
