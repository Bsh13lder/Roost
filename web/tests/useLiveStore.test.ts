import { describe, expect, it, vi, beforeEach } from "vitest";
import { renderHook } from "@testing-library/react";

// `useLiveStore.ts` always creates its socket through `createLiveStore()`
// (which reaches for the real `WebSocket` global) — mock that module so
// this test can inspect the singleton's lifecycle (created once, closed
// and dropped by `resetLiveStore`) without opening a real connection.
const { createLiveStoreMock } = vi.hoisted(() => {
  class FakeStore {
    connectCalls = 0;
    closeCalls = 0;
    connect() {
      this.connectCalls += 1;
    }
    close() {
      this.closeCalls += 1;
    }
    getState() {
      return { cursor: 0, bots: {}, messagesByThread: {}, streaming: {} };
    }
    subscribe(_listener: (state: unknown) => void) {
      return () => {};
    }
  }
  return { createLiveStoreMock: vi.fn(() => new FakeStore()) };
});

vi.mock("../src/store/live", () => ({
  createLiveStore: createLiveStoreMock,
}));

import { resetLiveStore, useLiveState } from "../src/hooks/useLiveStore";

beforeEach(() => {
  // Each test starts from a clean slate regardless of what a previous
  // test (or this module's own prior import) left behind.
  resetLiveStore();
  createLiveStoreMock.mockClear();
});

describe("useLiveStore singleton", () => {
  it("creates and connects exactly one store, reused across hook calls", () => {
    renderHook(() => useLiveState());
    renderHook(() => useLiveState());

    expect(createLiveStoreMock).toHaveBeenCalledTimes(1);
    const instance = createLiveStoreMock.mock.results[0]!.value;
    expect(instance.connectCalls).toBe(1);
  });

  it("resetLiveStore closes the current store so the next use creates a fresh one", () => {
    renderHook(() => useLiveState());
    const first = createLiveStoreMock.mock.results[0]!.value;
    expect(first.closeCalls).toBe(0);

    resetLiveStore();

    expect(first.closeCalls).toBe(1);

    renderHook(() => useLiveState());

    expect(createLiveStoreMock).toHaveBeenCalledTimes(2);
    const second = createLiveStoreMock.mock.results[1]!.value;
    expect(second).not.toBe(first);
    expect(second.connectCalls).toBe(1);
  });

  it("resetLiveStore is a harmless no-op when nothing was ever connected", () => {
    expect(() => resetLiveStore()).not.toThrow();
    expect(createLiveStoreMock).not.toHaveBeenCalled();
  });
});
