import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ComputerAsleep } from "../src/components/profile/ComputerAsleep";
import { makeBot } from "./fixtures";

function stubReducedMotion(reduced: boolean) {
  window.matchMedia = ((query: string) => ({
    matches: reduced && query === "(prefers-reduced-motion: reduce)", media: query, onchange: null,
    addListener: () => {}, removeListener: () => {}, addEventListener: () => {}, removeEventListener: () => {}, dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
}

afterEach(() => { cleanup(); stubReducedMotion(false); });

describe("ComputerAsleep", () => {
  it("shows the bot's robot asleep, Computer is asleep and Open it", () => {
    const { container } = render(<ComputerAsleep bot={makeBot({ name: "Scout" })} onOpen={vi.fn()} />);
    expect(container.querySelector(".robot")).toHaveAttribute("data-moment", "off");
    expect(screen.getByRole("heading", { name: "Computer is asleep" })).toBeInTheDocument();
    expect(screen.getByText("Scout's computer wakes when it needs it.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Open it" })).toBeInTheDocument();
    const zs = container.querySelectorAll(".computer-asleep__z");
    expect(zs).toHaveLength(3);
    zs.forEach((z) => expect(z).toHaveAttribute("aria-hidden", "true"));
    expect(container.querySelector(".computer-asleep")).not.toHaveClass("computer-asleep--still");
  });

  it("the z marks are still under reduced motion", () => {
    stubReducedMotion(true);
    const { container } = render(<ComputerAsleep bot={makeBot()} onOpen={vi.fn()} />);
    expect(container.querySelector(".computer-asleep")).toHaveClass("computer-asleep--still");
  });

  it("Open it starts the browser", async () => {
    const onOpen = vi.fn();
    render(<ComputerAsleep bot={makeBot()} onOpen={onOpen} />);
    await userEvent.click(screen.getByRole("button", { name: "Open it" }));
    expect(onOpen).toHaveBeenCalledTimes(1);
  });
});
