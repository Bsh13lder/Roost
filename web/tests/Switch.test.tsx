import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Switch } from "../src/ui/Switch";

afterEach(cleanup);

describe("Switch", () => {
  it("toggles with click and Space and reports aria-checked", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    const { rerender } = render(<Switch checked={false} onChange={onChange}>Split by project</Switch>);
    const toggle = screen.getByRole("switch", { name: "Split by project" });
    expect(toggle).toHaveAttribute("aria-checked", "false");
    await user.click(toggle);
    expect(onChange).toHaveBeenLastCalledWith(true);
    rerender(<Switch checked onChange={onChange}>Split by project</Switch>);
    expect(screen.getByRole("switch")).toHaveAttribute("aria-checked", "true");
    screen.getByRole("switch").focus();
    await user.keyboard(" ");
    expect(onChange).toHaveBeenLastCalledWith(false);
  });

  it("does nothing when disabled and keeps its title", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<Switch checked={false} disabled title="One row per project" onChange={onChange}>Split</Switch>);
    const toggle = screen.getByRole("switch");
    expect(toggle).toBeDisabled();
    expect(toggle).toHaveAttribute("title", "One row per project");
    await user.click(toggle);
    expect(onChange).not.toHaveBeenCalled();
  });
});
