import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Fold, FOLD_STORAGE_PREFIX } from "../src/ui/Fold";

beforeEach(() => window.localStorage.clear());
afterEach(cleanup);

describe("Fold", () => {
  it("starts closed, shows its summary, and opens and closes on a click", async () => {
    render(<Fold id="approval" title="Approval mode" summary="Auto-edit"><p>Inside</p></Fold>);
    const head = screen.getByRole("button", { name: /Approval mode/ });
    expect(head).toHaveAttribute("aria-expanded", "false");
    expect(head).toHaveTextContent("Auto-edit");
    expect(screen.queryByText("Inside")).not.toBeInTheDocument();
    await userEvent.click(head);
    expect(head).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("Inside")).toBeInTheDocument();
    await userEvent.click(head);
    expect(screen.queryByText("Inside")).not.toBeInTheDocument();
  });

  it("this browser remembers which folds are open", async () => {
    const { unmount } = render(<Fold id="memory" title="What I remember"><p>Inside</p></Fold>);
    await userEvent.click(screen.getByRole("button", { name: /What I remember/ }));
    expect(window.localStorage.getItem(`${FOLD_STORAGE_PREFIX}memory`)).toBe("1");
    unmount();
    render(<Fold id="memory" title="What I remember"><p>Inside</p></Fold>);
    expect(screen.getByText("Inside")).toBeInTheDocument();
  });

  it("still works when the browser refuses storage", async () => {
    const spy = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("blocked"); });
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    render(<Fold id="x" title="Decisions"><p>Inside</p></Fold>);
    await userEvent.click(screen.getByRole("button", { name: /Decisions/ }));
    expect(screen.getByText("Inside")).toBeInTheDocument();
    spy.mockRestore();
    warn.mockRestore();
  });
});
