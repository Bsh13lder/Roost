import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { GroupLabel } from "../src/components/panel/GroupLabel";
import { ApiError } from "../src/api/client";
import { makeBot } from "./fixtures";

const updateBotMock = vi.fn();
vi.mock("../src/api/bots", () => ({ updateBot: (id: string, patch: unknown) => updateBotMock(id, patch) }));

const onChange = vi.fn();
const show = (group: string | null, labels: string[] = []) =>
  render(<GroupLabel bot={makeBot({ id: "bot-1", group })} labels={labels} onChange={onChange} />);
const popover = () => screen.getByRole("dialog", { name: "Label" });

afterEach(() => { cleanup(); updateBotMock.mockReset(); onChange.mockReset(); });

describe("GroupLabel", () => {
  it("a bot with no label offers Add a label", async () => {
    show(null);
    await userEvent.click(screen.getByRole("button", { name: "Add a label" }));
    expect(within(popover()).getByRole("textbox", { name: "Label" })).toHaveValue("");
    expect(within(popover()).queryByRole("button", { name: "Remove label" })).not.toBeInTheDocument();
  });

  it("saves a typed label and shows it as the chip", async () => {
    const saved = makeBot({ id: "bot-1", group: "Work" });
    updateBotMock.mockResolvedValue(saved);
    const view = show(null);
    await userEvent.click(screen.getByRole("button", { name: "Add a label" }));
    await userEvent.type(within(popover()).getByRole("textbox", { name: "Label" }), "  Work {Enter}");
    expect(updateBotMock).toHaveBeenCalledWith("bot-1", { group: "Work" });
    expect(onChange).toHaveBeenCalledWith(saved);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    view.rerender(<GroupLabel bot={saved} labels={[]} onChange={onChange} />);
    expect(screen.getByRole("button", { name: "Work" })).toBeInTheDocument();
  });

  it("offers the labels other bots use in one tap", async () => {
    updateBotMock.mockResolvedValue(makeBot({ id: "bot-1", group: "Home" }));
    show(null, ["Home", "Work"]);
    await userEvent.click(screen.getByRole("button", { name: "Add a label" }));
    await userEvent.click(within(popover()).getByRole("button", { name: "Home" }));
    expect(updateBotMock).toHaveBeenCalledWith("bot-1", { group: "Home" });
    expect(onChange).toHaveBeenCalled();
  });

  it("Remove label clears it", async () => {
    updateBotMock.mockResolvedValue(makeBot({ id: "bot-1", group: null }));
    show("Work");
    await userEvent.click(screen.getByRole("button", { name: "Work" }));
    await userEvent.click(within(popover()).getByRole("button", { name: "Remove label" }));
    expect(updateBotMock).toHaveBeenCalledWith("bot-1", { group: "" });
    expect(onChange).toHaveBeenCalled();
  });

  it("refuses two lines or too long a label without asking the server", async () => {
    // A text box drops line breaks and stops at its maxLength, so the checks are reached through a tapped label.
    const long = "x".repeat(31);
    show(null, [long, "a\nb"]);
    await userEvent.click(screen.getByRole("button", { name: "Add a label" }));
    await userEvent.click(within(popover()).getByRole("button", { name: long }));
    expect(screen.getByText("A label is at most 30 characters.")).toBeInTheDocument();
    await userEvent.click(within(popover()).getByRole("button", { name: /^a\s*b$/ }));
    expect(screen.getByText("A label fits on one line.")).toBeInTheDocument();
    expect(updateBotMock).not.toHaveBeenCalled();
  });

  it("says the server's sentence and keeps your text when it refuses", async () => {
    updateBotMock.mockRejectedValue(new ApiError(422, "That label is not allowed."));
    show(null);
    await userEvent.click(screen.getByRole("button", { name: "Add a label" }));
    const box = within(popover()).getByRole("textbox", { name: "Label" });
    await userEvent.type(box, "Nope{Enter}");
    expect(await screen.findByText("That label is not allowed.")).toBeInTheDocument();
    expect(box).toHaveValue("Nope");
    expect(onChange).not.toHaveBeenCalled();
  });
});
