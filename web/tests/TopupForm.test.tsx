import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TopupForm } from "../src/components/projects/TopupForm";

const addTopupMock = vi.fn();
vi.mock("../src/api/projects", () => ({ addTopup: (...a: unknown[]) => addTopupMock(...a) }));

// Braces, so the hook returns nothing: vitest runs a function a beforeEach returns as its teardown,
// which here would call the mock again and throw its rejection.
beforeEach(() => { addTopupMock.mockReset(); });
afterEach(() => cleanup());

describe("TopupForm", () => {
  it("adds 50,00 from a gift, tells the page and clears", async () => {
    addTopupMock.mockResolvedValue({ id: "tu9" });
    const onAdded = vi.fn();
    const user = userEvent.setup();
    render(<TopupForm projectId="p1" onAdded={onAdded} />);
    await user.type(screen.getByLabelText("Top-up amount"), "50,00");
    await user.type(screen.getByLabelText("Where from"), "birthday gift");
    await user.click(screen.getByRole("button", { name: "Add top-up" }));
    expect(addTopupMock).toHaveBeenCalledWith("p1", { amount: "50.00", source: "birthday gift" });
    await waitFor(() => expect(onAdded).toHaveBeenCalledTimes(1));
    expect(screen.getByLabelText("Top-up amount")).toHaveValue("");
  });

  it("sends no source when none is given", async () => {
    addTopupMock.mockResolvedValue({ id: "tu9" });
    const user = userEvent.setup();
    render(<TopupForm projectId="p1" onAdded={vi.fn()} />);
    await user.type(screen.getByLabelText("Top-up amount"), "20");
    await user.click(screen.getByRole("button", { name: "Add top-up" }));
    expect(addTopupMock).toHaveBeenCalledWith("p1", { amount: "20.00" });
  });

  it("refuses an amount it can't read without calling the gateway", async () => {
    const user = userEvent.setup();
    render(<TopupForm projectId="p1" onAdded={vi.fn()} />);
    await user.type(screen.getByLabelText("Top-up amount"), "1.234,56");
    await user.click(screen.getByRole("button", { name: "Add top-up" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Enter an amount like 12,50.");
    expect(addTopupMock).not.toHaveBeenCalled();
  });

  it("shows the gateway's refusal", async () => {
    const { ApiError } = await import("../src/api/client");
    addTopupMock.mockRejectedValue(new ApiError(422, "An amount must be more than 0 and at most 1,000,000."));
    const user = userEvent.setup();
    render(<TopupForm projectId="p1" onAdded={vi.fn()} />);
    await user.type(screen.getByLabelText("Top-up amount"), "2000000");
    await user.click(screen.getByRole("button", { name: "Add top-up" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("at most 1,000,000");
  });
});
