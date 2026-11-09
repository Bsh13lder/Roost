import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ToastProvider, useToast } from "../src/ui/Toast";
import { TOAST_MS, UNDO_TOAST_MS } from "../src/ui/constants";

afterEach(() => { cleanup(); vi.useRealTimers(); });

function Saver() {
  const toast = useToast();
  return <button type="button" onClick={() => toast.show("Look saved", { tone: "ok" })}>Save look</button>;
}

describe("Toast", () => {
  it("says a note in one polite live region, and Dismiss takes it away", async () => {
    render(<ToastProvider><Saver /></ToastProvider>);
    await userEvent.click(screen.getByRole("button", { name: "Save look" }));
    const region = screen.getByRole("status");
    expect(region).toHaveAttribute("aria-live", "polite");
    expect(region).toHaveTextContent("Look saved");
    expect(region.querySelector(".toast--ok")).not.toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Dismiss" }));
    expect(region).not.toHaveTextContent("Look saved");
  });

  it("leaves by itself after its time", () => {
    vi.useFakeTimers();
    render(<ToastProvider><Saver /></ToastProvider>);
    act(() => screen.getByRole("button", { name: "Save look" }).click());
    expect(screen.getByRole("status")).toHaveTextContent("Look saved");
    act(() => { vi.advanceTimersByTime(4000); });
    expect(screen.getByRole("status")).not.toHaveTextContent("Look saved");
  });

  it("refuses to work without its provider, with a sentence that says where it is", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    expect(() => render(<Saver />)).toThrow("useToast needs a ToastProvider above it");
  });
});

describe("Toast with an action", () => {
  function Mover({ run }: { run: () => void }) {
    const toast = useToast();
    return <button type="button" onClick={() => toast.show("Moved", { action: { label: "Undo", run } })}>Move</button>;
  }

  it("runs the action once and closes", async () => {
    const run = vi.fn();
    render(<ToastProvider><Mover run={run} /></ToastProvider>);
    await userEvent.click(screen.getByRole("button", { name: "Move" }));
    await userEvent.click(screen.getByRole("button", { name: "Undo" }));
    expect(run).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("status")).not.toHaveTextContent("Moved");
  });

  it("an action toast stays for UNDO_TOAST_MS", () => {
    vi.useFakeTimers();
    render(<ToastProvider><Mover run={() => undefined} /></ToastProvider>);
    act(() => screen.getByRole("button", { name: "Move" }).click());
    act(() => { vi.advanceTimersByTime(UNDO_TOAST_MS - 1); });
    expect(screen.getByRole("status")).toHaveTextContent("Moved");
    act(() => { vi.advanceTimersByTime(2); });
    expect(screen.getByRole("status")).not.toHaveTextContent("Moved");
    expect(UNDO_TOAST_MS).toBeGreaterThan(TOAST_MS);
  });
});

describe("Toast replacing (lead 01b)", () => {
  function Many() {
    const toast = useToast();
    return (
      <>
        <button type="button" onClick={() => toast.show("Saved the list", { action: { label: "Undo", run: () => undefined } })}>One</button>
        <button type="button" onClick={() => toast.show("Saved the priority", { action: { label: "Undo", run: () => undefined } })}>Two</button>
        <button type="button" onClick={() => toast.show("Couldn't save", { tone: "danger", action: { label: "Try again", run: () => undefined } })}>Fail</button>
        <button type="button" onClick={() => toast.show("A plain note")}>Note</button>
      </>
    );
  }

  it("a newer Undo toast replaces the older one; other toasts stay", async () => {
    render(<ToastProvider><Many /></ToastProvider>);
    await userEvent.click(screen.getByRole("button", { name: "Fail" }));
    await userEvent.click(screen.getByRole("button", { name: "Note" }));
    await userEvent.click(screen.getByRole("button", { name: "One" }));
    await userEvent.click(screen.getByRole("button", { name: "Two" }));
    const region = screen.getByRole("status");
    expect(region).not.toHaveTextContent("Saved the list");
    expect(region).toHaveTextContent("Saved the priority");
    expect(screen.getAllByRole("button", { name: "Undo" })).toHaveLength(1);
    expect(region).toHaveTextContent("Couldn't save");
    expect(region).toHaveTextContent("A plain note");
  });
});
