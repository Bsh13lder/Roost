import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen } from "@testing-library/react";
import { WorkingTimer, formatElapsed } from "../src/components/WorkingIndicator";

afterEach(() => { cleanup(); vi.useRealTimers(); });

describe("WorkingIndicator", () => {
  it("formats elapsed time compactly", () => {
    expect(formatElapsed(42_000)).toBe("42s");
    expect(formatElapsed(65_000)).toBe("1m 05s");
    expect(formatElapsed(-5)).toBe("0s");
  });
  it("the timer counts up once a second", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-10-14T10:00:10Z"));
    render(<WorkingTimer since={Date.parse("2026-10-14T10:00:00Z")} />);
    expect(screen.getByText("10s")).toBeInTheDocument();
    act(() => { vi.advanceTimersByTime(2000); });
    expect(screen.getByText("12s")).toBeInTheDocument();
  });
});
