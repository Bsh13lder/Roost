import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Composer } from "../src/components/Composer";
import { matchingOptions } from "../src/lib/mentions";

afterEach(() => cleanup());

const TEAM = [{ id: "s", name: "Scout" }, { id: "q", name: "Quill" }];

describe("matchingOptions", () => {
  it("lists the names that start with what is typed, and nothing without an @word", () => {
    expect(matchingOptions("sc", TEAM)).toEqual([{ id: "s", name: "Scout" }]);
    expect(matchingOptions("", TEAM)).toEqual(TEAM);
    expect(matchingOptions(null, TEAM)).toEqual([]);
  });
});

describe("Composer @ list", () => {
  it("typing @ lists your other bots and Enter picks one without sending", async () => {
    const onSend = vi.fn();
    render(<Composer onSend={onSend} mentions={TEAM} />);
    const box = screen.getByRole("textbox");
    await userEvent.type(box, "@");
    expect(screen.getAllByRole("option").map((o) => o.textContent)).toEqual(["@Scout", "@Quill"]);
    await userEvent.keyboard("{ArrowDown}{Enter}");
    expect(box).toHaveValue("@Quill ");
    expect(onSend).not.toHaveBeenCalled();
    expect(screen.queryByRole("listbox")).toBeNull();
    await userEvent.type(box, "hi{Enter}");
    expect(onSend).toHaveBeenCalledWith("@Quill hi", { spoken: false });
  });

  it("a click picks, Escape closes, and with no mentions there is never a list", async () => {
    const { unmount } = render(<Composer onSend={vi.fn()} mentions={TEAM} />);
    const box = screen.getByRole("textbox");
    await userEvent.type(box, "ask @Sc");
    await userEvent.pointer({ keys: "[MouseLeft>]", target: screen.getByRole("option", { name: "@Scout" }) });
    expect(box).toHaveValue("ask @Scout ");
    await userEvent.type(box, "@");
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("listbox")).toBeNull();
    unmount();
    render(<Composer onSend={vi.fn()} />);
    await userEvent.type(screen.getByRole("textbox"), "@");
    expect(screen.queryByRole("listbox")).toBeNull();
  });
});
