import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { Menu, MenuItem } from "../src/ui/Menu";
import { Select } from "../src/ui/Select";
import { Sheet } from "../src/ui/Sheet";
import { MoreIcon } from "../src/components/icons";

afterEach(() => cleanup());

// P1 review: a Sheet opened from a menu item gave focus to the page body when it closed, because the
// item is gone by the time the Sheet remembers what opened it.
function RowWithMenu({ onOther }: { onOther: () => void }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Menu label="More for Fix the sink" trigger={<MoreIcon />}>
        <MenuItem onSelect={() => setOpen(true)}>Open details</MenuItem>
        <MenuItem onSelect={onOther}>Copy link</MenuItem>
      </Menu>
      <Sheet open={open} onOpenChange={setOpen} title="Fix the sink"><input aria-label="Title" /></Sheet>
    </>
  );
}

describe("a Sheet opened from a menu item (redesign P3)", () => {
  it("gives focus back to the menu's button when it closes", async () => {
    const user = userEvent.setup();
    render(<RowWithMenu onOther={vi.fn()} />);
    const button = screen.getByRole("button", { name: "More for Fix the sink" });
    await user.click(button);
    await user.click(await screen.findByRole("menuitem", { name: "Open details" }));
    const sheet = await screen.findByRole("dialog", { name: "Fix the sink" });
    expect(sheet).toContainElement(document.activeElement as HTMLElement);
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(button).toHaveFocus();
  });

  it("an item that opens nothing still runs and leaves focus on the menu's button", async () => {
    const onOther = vi.fn();
    const user = userEvent.setup();
    render(<RowWithMenu onOther={onOther} />);
    const button = screen.getByRole("button", { name: "More for Fix the sink" });
    await user.click(button);
    await user.click(await screen.findByRole("menuitem", { name: "Copy link" }));
    expect(onOther).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
    expect(button).toHaveFocus();
  });
});

function SheetWithPickers() {
  const [priority, setPriority] = useState("medium");
  return (
    <Sheet open onOpenChange={() => undefined} title="Fix the sink">
      <Select label="Priority" value={priority} onChange={setPriority}
        options={[{ value: "medium", label: "Medium" }, { value: "high", label: "High" }]} />
      <Menu label="More" trigger={<MoreIcon />}><MenuItem onSelect={() => undefined}>Copy link</MenuItem></Menu>
    </Sheet>
  );
}

describe("overlays inside a Sheet (redesign P3)", () => {
  it("a Select opens inside the Sheet's panel and picks, and the Sheet stays open", async () => {
    const user = userEvent.setup();
    render(<SheetWithPickers />);
    const sheet = screen.getByRole("dialog", { name: "Fix the sink" });
    const priority = within(sheet).getByRole("combobox", { name: "Priority" });
    await user.click(priority);
    expect(sheet).toContainElement(await screen.findByRole("listbox"));
    await user.click(screen.getByRole("option", { name: "High" }));
    expect(priority).toHaveTextContent("High");
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
    expect(screen.getByRole("dialog", { name: "Fix the sink" })).toBeInTheDocument();
  });

  it("a Menu opens inside the Sheet's panel", async () => {
    const user = userEvent.setup();
    render(<SheetWithPickers />);
    const sheet = screen.getByRole("dialog", { name: "Fix the sink" });
    await user.click(within(sheet).getByRole("button", { name: "More" }));
    expect(sheet).toContainElement(await screen.findByRole("menu"));
  });
});

describe("a full-screen Sheet (polish R1)", () => {
  it("keeps focus inside and gives it back when it closes", async () => {
    const user = userEvent.setup();
    function Full() {
      const [open, setOpen] = useState(false);
      return (
        <>
          <button onClick={() => setOpen(true)}>Open profile</button>
          <Sheet open={open} onOpenChange={setOpen} size="full" title="Scout's profile"><input aria-label="Name" /></Sheet>
        </>
      );
    }
    render(<Full />);
    const opener = screen.getByRole("button", { name: "Open profile" });
    await user.click(opener);
    const sheet = await screen.findByRole("dialog", { name: "Scout's profile" });
    expect(sheet).toHaveClass("ui-sheet--full");
    expect(sheet).toContainElement(document.activeElement as HTMLElement);
    await user.tab();
    await user.tab();
    await user.tab();
    expect(sheet).toContainElement(document.activeElement as HTMLElement);
    await user.keyboard("{Escape}");
    expect(opener).toHaveFocus();
  });
});
