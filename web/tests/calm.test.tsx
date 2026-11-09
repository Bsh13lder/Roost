import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, renderHook, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { CALM_STORAGE_KEY, calmSetting, readCalm, setCalmSetting, writeCalm } from "../src/lib/calm";
import { useApplyCalm, useCalmSetting } from "../src/hooks/useCalmRobots";
import { SidebarFoot } from "../src/components/sidebar/SidebarFoot";

vi.mock("../src/hooks/useAuth", () => ({ useAuth: () => ({ user: { username: "blckit" }, logout: vi.fn() }) }));
vi.mock("../src/hooks/useAttention", () => ({ useNotificationPermission: () => ["granted", vi.fn()] }));
vi.mock("../src/api/connectors", () => ({ listConnectors: () => Promise.resolve([]) }));
vi.mock("../src/api/mac", () => ({ listGrants: () => Promise.resolve([]) }));

function mockReducedMotion(reduce: boolean) {
  window.matchMedia = ((query: string) => ({
    matches: reduce && query.includes("prefers-reduced-motion"),
    media: query,
    addEventListener: () => {},
    removeEventListener: () => {},
  })) as unknown as typeof window.matchMedia;
}

afterEach(() => {
  cleanup();
  localStorage.clear();
  setCalmSetting(false);
  document.documentElement.classList.remove("calm");
  mockReducedMotion(false);
});

describe("Calm robots (the setting)", () => {
  it("is off until this browser says otherwise, and remembers a choice", () => {
    expect(readCalm()).toBe(false);
    writeCalm(true);
    expect(localStorage.getItem(CALM_STORAGE_KEY)).toBe("true");
    expect(readCalm()).toBe(true);
    writeCalm(false);
    expect(readCalm()).toBe(false);
  });

  it("survives a browser that refuses or garbles storage", () => {
    const throwing = { getItem: () => { throw new Error("blocked"); }, setItem: () => { throw new Error("blocked"); } };
    expect(readCalm(throwing)).toBe(false);
    expect(() => writeCalm(true, throwing)).not.toThrow();
    expect(readCalm({ getItem: () => "sideways", setItem: () => {} })).toBe(false);
  });

  it("the hook follows the setting and writes it", () => {
    const { result } = renderHook(() => useCalmSetting());
    expect(result.current[0]).toBe(false);
    act(() => result.current[1](true));
    expect(result.current[0]).toBe(true);
    expect(calmSetting()).toBe(true);
    expect(readCalm()).toBe(true);
  });

  it("marks the page calm for the setting or for reduced motion, and clears it otherwise", () => {
    mockReducedMotion(false);
    const { unmount } = renderHook(() => useApplyCalm());
    expect(document.documentElement).not.toHaveClass("calm");
    act(() => setCalmSetting(true));
    expect(document.documentElement).toHaveClass("calm");
    act(() => setCalmSetting(false));
    expect(document.documentElement).not.toHaveClass("calm");
    unmount();
    mockReducedMotion(true);
    renderHook(() => useApplyCalm());
    expect(document.documentElement).toHaveClass("calm");
  });

  it("is a switch in Settings (behind your initials), stored in this browser", async () => {
    render(<MemoryRouter><SidebarFoot /></MemoryRouter>);
    await userEvent.click(screen.getByRole("button", { name: "Settings" }));
    const item = await screen.findByRole("switch", { name: "Calm robots" });
    expect(item).toHaveAttribute("aria-checked", "false");
    await userEvent.click(item);
    expect(readCalm()).toBe(true);
    expect(screen.getByRole("switch", { name: "Calm robots" })).toHaveAttribute("aria-checked", "true");
  });
});
