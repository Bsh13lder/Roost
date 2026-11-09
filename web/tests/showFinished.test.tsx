import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ShowFinishedSwitch } from "../src/components/ShowFinishedSwitch";
import { useShowFinished, SHOW_FINISHED_STORAGE_KEY } from "../src/hooks/useShowFinished";
import { isFinished, keepShown } from "../src/lib/finished";

afterEach(() => { cleanup(); window.localStorage.clear(); vi.restoreAllMocks(); });

function Reader({ name }: { name: string }) {
  const [show] = useShowFinished();
  return <output aria-label={name}>{show ? "on" : "off"}</output>;
}

describe("finished tasks", () => {
  it("are the closed ones: done, failed, cancelled; a row with no status counts as open", () => {
    expect(["todo", "in_progress", "done", "failed", "cancelled"].map((status) => isFinished({ status })))
      .toEqual([false, false, true, true, true]);
    expect(isFinished({})).toBe(false);
  });

  it("keepShown drops them unless they are shown, keeping the order", () => {
    const rows = [{ id: "a", status: "done" }, { id: "b", status: "todo" }, { id: "c", status: "failed" }];
    expect(keepShown(rows, false).map((row) => row.id)).toEqual(["b"]);
    expect(keepShown(rows, true)).toBe(rows);
  });
});

describe("the Show finished switch", () => {
  it("is off by default, and every view hears a change at once", async () => {
    render(<><ShowFinishedSwitch /><Reader name="list" /><Reader name="calendar" /></>);
    const toggle = screen.getByRole("switch", { name: "Show finished" });
    expect(toggle).toHaveAttribute("aria-checked", "false");
    await userEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-checked", "true");
    expect(screen.getByRole("status", { name: "list" })).toHaveTextContent("on");
    expect(screen.getByRole("status", { name: "calendar" })).toHaveTextContent("on");
    expect(window.localStorage.getItem(SHOW_FINISHED_STORAGE_KEY)).toBe("1");
  });

  it("is remembered in this browser", () => {
    window.localStorage.setItem(SHOW_FINISHED_STORAGE_KEY, "1");
    render(<ShowFinishedSwitch />);
    expect(screen.getByRole("switch", { name: "Show finished" })).toHaveAttribute("aria-checked", "true");
  });

  it("follows another tab", () => {
    render(<Reader name="list" />);
    act(() => {
      window.localStorage.setItem(SHOW_FINISHED_STORAGE_KEY, "1");
      window.dispatchEvent(new StorageEvent("storage", { key: SHOW_FINISHED_STORAGE_KEY, newValue: "1" }));
    });
    expect(screen.getByRole("status", { name: "list" })).toHaveTextContent("on");
  });

  it("says how many finished tasks it hides while off", async () => {
    const { rerender } = render(<ShowFinishedSwitch hidden={3} />);
    expect(screen.getByText("3 finished hidden")).toBeInTheDocument();
    rerender(<ShowFinishedSwitch hidden={0} />);
    expect(screen.queryByText(/finished hidden/)).not.toBeInTheDocument();
    rerender(<ShowFinishedSwitch hidden={2} />);
    await userEvent.click(screen.getByRole("switch", { name: "Show finished" }));
    expect(screen.queryByText(/finished hidden/)).not.toBeInTheDocument();
  });

  it("still works for this visit when the browser refuses storage", async () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("full"); });
    vi.spyOn(console, "warn").mockImplementation(() => undefined);
    render(<ShowFinishedSwitch />);
    await userEvent.click(screen.getByRole("switch", { name: "Show finished" }));
    expect(screen.getByRole("switch", { name: "Show finished" })).toHaveAttribute("aria-checked", "true");
    await userEvent.click(screen.getByRole("switch", { name: "Show finished" })); // back off for the next test
  });
});
