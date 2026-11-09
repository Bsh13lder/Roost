import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { FirstLine, workingWords } from "../src/components/chat/FirstLine";
import type { AvatarOut } from "../src/api/types";

afterEach(() => { cleanup(); });

const NOW = () => Date.now();
const AVATAR = { shape: "mochi", color: "#22c55e", accessory: "none" } as unknown as AvatarOut;

describe("FirstLine", () => {
  it("shows streamed text at once", () => {
    render(<FirstLine text="Checking." activity="reading" since={NOW()} />);
    expect(screen.getByText("Checking.")).toBeInTheDocument();
    expect(screen.queryByText(/reading/i)).not.toBeInTheDocument();
  });

  it("shows the bot's robot at work with what it is doing, never 'On it' text", () => {
    const { container } = render(<FirstLine text="" activity="checking your inbox" since={NOW()} avatar={AVATAR} name="Gela" />);
    expect(screen.getByText("Checking your inbox…")).toBeInTheDocument();
    expect(screen.getByRole("status", { name: "Gela: Checking your inbox…" })).toBeInTheDocument();
    const robot = container.querySelector("svg.working-bot");
    expect(robot?.getAttribute("data-moment")).toBe("onit");
    expect(robot?.getAttribute("data-doing")).toBe("think");
    expect(container.querySelector(".working-timer")).not.toBeNull();
    expect(screen.queryByText(/On it/)).not.toBeInTheDocument();
  });

  it("says what it does in a sentence even with no activity yet", () => {
    render(<FirstLine text="" activity={null} since={NOW()} />);
    expect(screen.getByText("Reading your message…")).toBeInTheDocument();
    expect(workingWords("opening the chat.")).toBe("Opening the chat…");
  });
});
