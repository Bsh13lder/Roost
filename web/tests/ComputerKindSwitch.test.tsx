import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ComputerKindSwitch } from "../src/components/computer/ComputerKindSwitch";
import { makeBot } from "./fixtures";

const setComputerMock = vi.fn();
vi.mock("../src/api/bots", () => ({ setComputer: (id: string, kind: string) => setComputerMock(id, kind) }));

afterEach(() => { cleanup(); setComputerMock.mockReset(); });

describe("ComputerKindSwitch", () => {
  it("switches to Mac Brave and back, saying what each does", async () => {
    const onChange = vi.fn();
    setComputerMock.mockImplementation(async (_id: string, kind: "linux" | "mac_brave") => makeBot({ computer: kind }));
    const { rerender } = render(<ComputerKindSwitch bot={makeBot({ computer: "mac_brave" })} onChange={onChange} />);
    expect(screen.getByText("Optional: its own Brave window on your Mac.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Linux computer" }));
    expect(setComputerMock).toHaveBeenCalledWith("bot-1", "linux");
    expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ computer: "linux" }));
    rerender(<ComputerKindSwitch bot={makeBot({ computer: "linux" })} onChange={onChange} />);
    expect(screen.getByText("The usual choice: a sealed Linux computer on this Mac. Sign in once with Take control.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Mac Brave (optional)" }));
    expect(setComputerMock).toHaveBeenLastCalledWith("bot-1", "mac_brave");
  });

  it("Linux comes first as the usual choice, Mac Brave is the optional one", () => {
    render(<ComputerKindSwitch bot={makeBot({ computer: "linux" })} onChange={vi.fn()} />);
    const names = screen.getAllByRole("button").map((button) => button.textContent);
    expect(names).toEqual(["Linux computer", "Mac Brave (optional)"]);
  });

  it("shows the server's refusal and keeps the old choice", async () => {
    const { ApiError } = await import("../src/api/client");
    const onChange = vi.fn();
    setComputerMock.mockRejectedValue(new ApiError(409, "Finish the current run first."));
    render(<ComputerKindSwitch bot={makeBot({ computer: "mac_brave" })} onChange={onChange} />);
    await userEvent.click(screen.getByRole("button", { name: "Linux computer" }));
    expect(await screen.findByText("Finish the current run first.")).toBeInTheDocument();
    expect(onChange).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Mac Brave (optional)" })).toHaveAttribute("aria-pressed", "true");
  });
});
