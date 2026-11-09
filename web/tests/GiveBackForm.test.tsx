import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { GiveBackForm } from "../src/components/computer/GiveBackForm";

afterEach(cleanup);

describe("GiveBackForm", () => {
  it("gives it back with or without an account", async () => {
    const onConfirm = vi.fn();
    render(<GiveBackForm host="shop.example" busy={false} error={null} onConfirm={onConfirm} onBack={() => {}} />);
    expect(screen.getByLabelText(/Which account did you use\?/)).toBeInTheDocument();
    expect(screen.getByText(/shop\.example/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Give it back" }));
    expect(onConfirm).toHaveBeenLastCalledWith(undefined);
    await userEvent.type(screen.getByLabelText(/Which account did you use\?/), "  work email ");
    await userEvent.click(screen.getByRole("button", { name: "Give it back" }));
    expect(onConfirm).toHaveBeenLastCalledWith("work email");
  });

  it("refuses an account over 100 characters", async () => {
    const onConfirm = vi.fn();
    render(<GiveBackForm busy={false} error={null} onConfirm={onConfirm} onBack={() => {}} />);
    await userEvent.click(screen.getByLabelText(/Which account did you use\?/));
    await userEvent.paste("a".repeat(101));
    await userEvent.click(screen.getByRole("button", { name: "Give it back" }));
    expect(onConfirm).not.toHaveBeenCalled();
    expect(screen.getByText(/100 characters/)).toBeInTheDocument();
  });

  it("Back returns to the bar", async () => {
    const onBack = vi.fn();
    render(<GiveBackForm busy={false} error={null} onConfirm={() => {}} onBack={onBack} />);
    await userEvent.click(screen.getByRole("button", { name: "Back" }));
    expect(onBack).toHaveBeenCalled();
  });
});
