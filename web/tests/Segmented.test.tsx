import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Segmented } from "../src/ui/Segmented";

afterEach(() => cleanup());

const OPTIONS = [{ id: "list", label: "List" }, { id: "kanban", label: "Kanban" }, { id: "cal", label: "Calendar" }] as const;

describe("Segmented", () => {
  it("marks the chosen option pressed and moves with arrow keys", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<Segmented label="Task layout" options={OPTIONS} value="list" onChange={onChange} />);
    const group = screen.getByRole("group", { name: "Task layout" });
    expect(group).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "List" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Kanban" })).toHaveAttribute("aria-pressed", "false");
    screen.getByRole("button", { name: "List" }).focus();
    await user.keyboard("{ArrowRight}");
    expect(onChange).toHaveBeenLastCalledWith("kanban");
    expect(screen.getByRole("button", { name: "Kanban" })).toHaveFocus();
    await user.keyboard("{ArrowLeft}");
    expect(onChange).toHaveBeenLastCalledWith("list");
    await user.keyboard("{ArrowLeft}");
    expect(onChange).toHaveBeenLastCalledWith("cal"); // wraps round from the first
  });

  it("clicking an option chooses it", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<Segmented label="Task layout" options={OPTIONS} value="list" onChange={onChange} />);
    await user.click(screen.getByRole("button", { name: "Calendar" }));
    expect(onChange).toHaveBeenCalledWith("cal");
  });
});
