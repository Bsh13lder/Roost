import { describe, expect, it, vi, afterEach } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import { ComputerPanel } from "../src/components/ComputerPanel";
import type { DeskStatusOut } from "../src/api/types";

afterEach(() => cleanup());

const STATUS: DeskStatusOut = { browser: "stopped", workspace: "absent" };

function renderPanel() {
  return render(<ComputerPanel status={STATUS} onStartBrowser={vi.fn()} onStopBrowser={vi.fn()} />);
}

describe("ComputerPanel", () => {
  it("shows the window's state inside its own Window card, with Open window and Close window", () => {
    renderPanel();
    const card = screen.getByRole("region", { name: "Window" });
    expect(within(card).getByText("stopped")).toBeInTheDocument();
    expect(within(card).getByRole("button", { name: "Open window" })).toBeInTheDocument();
    expect(within(card).getByRole("button", { name: "Close window" })).toBeInTheDocument();
    expect(within(card).getByText("This bot’s own Brave window on your Mac, kept apart from yours.")).toBeInTheDocument();
  });

  it("never says desk to the user", () => {
    const { container } = renderPanel();
    expect(container.textContent ?? "").not.toMatch(/desk/i);
  });

  it("has no sealed box and no command line", () => {
    renderPanel();
    expect(screen.queryByRole("region", { name: "Sealed box" })).toBeNull();
    expect(screen.queryByRole("textbox", { name: "Command" })).toBeNull();
    expect(screen.queryByText(/sealed box/i)).toBeNull();
  });
});
