import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { IconButton } from "../src/ui/IconButton";
import { Popover } from "../src/ui/Popover";
import { Sheet } from "../src/ui/Sheet";
import { Tooltip } from "../src/ui/Tooltip";
import { CalendarIcon, PlusIcon } from "../src/components/icons";

afterEach(() => cleanup());

function TaskSheet() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>Open task</button>
      <Sheet open={open} onOpenChange={setOpen} title="Call the dentist" description="Due tomorrow">
        <input aria-label="Title" />
      </Sheet>
    </>
  );
}

describe("Sheet", () => {
  it("opens as a named modal dialog with Close, and Escape gives focus back to its opener", async () => {
    const user = userEvent.setup();
    render(<TaskSheet />);
    const opener = screen.getByRole("button", { name: "Open task" });
    await user.click(opener);
    const sheet = screen.getByRole("dialog", { name: "Call the dentist" });
    expect(sheet).toHaveClass("ui-sheet");
    expect(sheet).toHaveAccessibleDescription("Due tomorrow");
    expect(screen.getByRole("button", { name: "Close" })).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(opener).toHaveFocus();
  });

  it("Close closes it", async () => {
    render(<TaskSheet />);
    await userEvent.click(screen.getByRole("button", { name: "Open task" }));
    await userEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});

describe("Popover", () => {
  it("opens a named panel from an icon button and closes on Escape, focus back on the button", async () => {
    const user = userEvent.setup();
    render(
      <Popover label="Pick a day" trigger={<IconButton label="Open calendar" icon={<CalendarIcon />} />}>
        <button type="button">Tomorrow</button>
      </Popover>,
    );
    const button = screen.getByRole("button", { name: "Open calendar" });
    await user.click(button);
    expect(screen.getByRole("dialog", { name: "Pick a day" })).toBeInTheDocument();
    expect(button).toHaveAttribute("aria-expanded", "true");
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog", { name: "Pick a day" })).not.toBeInTheDocument();
    expect(button).toHaveFocus();
  });
});

describe("Popover on an anchor", () => {
  it("a popover can open on an anchor without a trigger", async () => {
    const user = userEvent.setup();
    function Cell() {
      const [open, setOpen] = useState(false);
      return (
        <Popover label="Wed 21 Oct" open={open} onOpenChange={setOpen}
          anchor={<div role="gridcell" aria-label="Wed 21 Oct" onClick={() => setOpen(true)}>21</div>}>
          <p>Day panel</p>
        </Popover>
      );
    }
    render(<Cell />);
    await user.click(screen.getByRole("gridcell", { name: "Wed 21 Oct" }));
    expect(screen.getByRole("dialog", { name: "Wed 21 Oct" })).toHaveTextContent("Day panel");
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});

describe("Tooltip and IconButton", () => {
  it("an icon button's tooltip says its name on keyboard focus", async () => {
    const user = userEvent.setup();
    render(<IconButton label="New chat" icon={<PlusIcon />} />);
    await user.tab();
    expect(screen.getByRole("button", { name: "New chat" })).toHaveFocus();
    expect(await screen.findByRole("tooltip")).toHaveTextContent("New chat");
  });

  it("a tooltip leaves its element's own name alone", async () => {
    const user = userEvent.setup();
    render(<Tooltip content="Saves at once"><button type="button">Save</button></Tooltip>);
    await user.hover(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("tooltip")).toHaveTextContent("Saves at once");
    expect(screen.getByRole("button", { name: "Save" })).toBeInTheDocument();
  });
});
