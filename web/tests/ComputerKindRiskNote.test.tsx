import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { ComputerKindSwitch } from "../src/components/computer/ComputerKindSwitch";
import { makeBot } from "./fixtures";

vi.mock("../src/api/bots", () => ({ setComputer: vi.fn() }));
afterEach(cleanup);

const RISK = "Mac Brave runs as your macOS user. The Linux computer is sealed off.";

describe("ComputerKindSwitch risk note", () => {
  it("shows the risk line when Mac Brave is selected", () => {
    render(<ComputerKindSwitch bot={makeBot({ computer: "mac_brave" })} onChange={vi.fn()} />);
    expect(screen.getByText(RISK)).toBeInTheDocument();
  });

  it("hides it on the Linux computer", () => {
    render(<ComputerKindSwitch bot={makeBot({ computer: "linux" })} onChange={vi.fn()} />);
    expect(screen.queryByText(RISK)).toBeNull();
  });
});
