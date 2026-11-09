import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useEffect, useRef, useState } from "react";
import { MemoryRouter } from "react-router-dom";
import { Menu, MenuItem, MenuLink, MenuNote } from "../src/ui/Menu";

afterEach(() => cleanup());

function renderMenu(onStop = vi.fn()) {
  render(
    <MemoryRouter>
      <Menu label="Scout menu" trigger="⋯">
        <MenuNote>Signed in as ana</MenuNote>
        <MenuItem onSelect={onStop}>Stop</MenuItem>
        <MenuItem onSelect={vi.fn()} disabled title="Make another bot the main bot first.">Retire this bot</MenuItem>
        <MenuLink to="/bots/new">New bot</MenuLink>
      </Menu>
    </MemoryRouter>,
  );
  return onStop;
}

describe("Menu", () => {
  it("opens from its button and lists its items, notes and links", async () => {
    renderMenu();
    const button = screen.getByRole("button", { name: "Scout menu" });
    expect(button).toHaveAttribute("aria-haspopup", "menu");
    await userEvent.click(button);
    expect(screen.getByRole("menu", { name: "Scout menu" })).toBeInTheDocument();
    expect(screen.getByText("Signed in as ana")).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "New bot" })).toHaveAttribute("href", "/bots/new");
    expect(screen.getByRole("menuitem", { name: "Retire this bot" })).toHaveAttribute("aria-disabled", "true");
  });

  it("picking an item runs it and closes the menu", async () => {
    const onStop = renderMenu();
    await userEvent.click(screen.getByRole("button", { name: "Scout menu" }));
    await userEvent.click(screen.getByRole("menuitem", { name: "Stop" }));
    expect(onStop).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });

  it("works from the keyboard: Enter opens, arrows skip the disabled item, Escape gives focus back", async () => {
    const onStop = renderMenu();
    const user = userEvent.setup();
    const button = screen.getByRole("button", { name: "Scout menu" });
    button.focus();
    await user.keyboard("{Enter}");
    await waitFor(() => expect(screen.getByRole("menuitem", { name: "Stop" })).toHaveFocus());
    await user.keyboard("{ArrowDown}");
    expect(screen.getByRole("menuitem", { name: "New bot" })).toHaveFocus();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
    await waitFor(() => expect(button).toHaveFocus());
    expect(onStop).not.toHaveBeenCalled();
  });

  it("leaves focus where the chosen item's action put it", async () => {
    function RoomName() { // like NewRoomDialog: it focuses its field once it has mounted
      const field = useRef<HTMLInputElement>(null);
      useEffect(() => field.current?.focus(), []);
      return <input ref={field} aria-label="Room name" />;
    }
    function WithDialog() {
      const [open, setOpen] = useState(false);
      return (
        <MemoryRouter>
          <Menu label="New" trigger="+"><MenuItem onSelect={() => setOpen(true)}>New room</MenuItem></Menu>
          {open ? <RoomName /> : null}
        </MemoryRouter>
      );
    }
    render(<WithDialog />);
    await userEvent.click(screen.getByRole("button", { name: "New" }));
    await userEvent.click(screen.getByRole("menuitem", { name: "New room" }));
    const field = await screen.findByRole("textbox", { name: "Room name" });
    await waitFor(() => expect(field).toHaveFocus());
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(field).toHaveFocus();
  });
});
