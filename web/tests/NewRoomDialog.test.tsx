import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NewRoomDialog } from "../src/components/NewRoomDialog";
import { makeBot } from "./fixtures";

const createRoomMock = vi.fn();
vi.mock("../src/api/rooms", () => ({ createRoom: (...args: unknown[]) => createRoomMock(...args) }));

const CHIEF = makeBot({ id: "c", name: "Chief", is_primary: true });
const SCOUT = makeBot({ id: "s", name: "Scout" });
const QUILL = makeBot({ id: "q", name: "Quill" });
const NAPPING = makeBot({ id: "n", name: "Nap", off_duty: true, status: "off_duty" });

beforeEach(() => createRoomMock.mockReset());
afterEach(() => cleanup());

function setup() {
  const onClose = vi.fn();
  const onCreated = vi.fn();
  render(<NewRoomDialog bots={[SCOUT, QUILL, CHIEF, NAPPING]} onClose={onClose} onCreated={onCreated} />);
  return { onClose, onCreated, dialog: screen.getByRole("dialog", { name: "New room" }) };
}

describe("NewRoomDialog", () => {
  it("needs a name and at least two bots, and refuses off-duty bots", async () => {
    setup();
    const create = screen.getByRole("button", { name: "Create room" });
    expect(create).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Room name"), "Saturday");
    await userEvent.click(screen.getByRole("checkbox", { name: "Scout" }));
    expect(create).toBeDisabled();
    expect(screen.getByRole("checkbox", { name: /Nap/ })).toBeDisabled();
  });

  it("makes the main bot the coordinator by default and creates the room", async () => {
    const { onCreated } = setup();
    createRoomMock.mockResolvedValue({ id: "r1", name: "Saturday" });
    await userEvent.type(screen.getByLabelText("Room name"), "Saturday");
    for (const name of ["Chief", "Scout", "Quill"]) await userEvent.click(screen.getByRole("checkbox", { name }));
    expect(screen.getByRole("combobox", { name: "Coordinator" })).toHaveTextContent("Chief");
    await userEvent.click(screen.getByRole("button", { name: "Create room" }));
    expect(createRoomMock).toHaveBeenCalledWith({ name: "Saturday", member_ids: ["c", "s", "q"], coordinator_id: "c" });
    expect(onCreated).toHaveBeenCalledWith({ id: "r1", name: "Saturday" });
  });

  it("Escape closes the open Coordinator list, not the dialog", async () => {
    const { onClose } = setup();
    for (const name of ["Chief", "Scout"]) await userEvent.click(screen.getByRole("checkbox", { name }));
    await userEvent.click(screen.getByRole("combobox", { name: "Coordinator" }));
    expect(screen.getByRole("listbox")).toBeInTheDocument();
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog", { name: "New room" })).toBeInTheDocument();
  });

  it("picks another coordinator from the list", async () => {
    createRoomMock.mockResolvedValue({ id: "r1", name: "Saturday" });
    setup();
    await userEvent.type(screen.getByLabelText("Room name"), "Saturday");
    for (const name of ["Chief", "Scout"]) await userEvent.click(screen.getByRole("checkbox", { name }));
    await userEvent.click(screen.getByRole("combobox", { name: "Coordinator" }));
    await userEvent.click(screen.getByRole("option", { name: "Scout" }));
    await userEvent.click(screen.getByRole("button", { name: "Create room" }));
    expect(createRoomMock).toHaveBeenCalledWith({ name: "Saturday", member_ids: ["c", "s"], coordinator_id: "s" });
  });

  it("closes with Escape and moves focus into the name field", async () => {
    const { onClose } = setup();
    expect(screen.getByLabelText("Room name")).toHaveFocus();
    await userEvent.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalled();
  });

  it("keeps Tab inside the dialog and gives focus back to its opener on close", async () => {
    const opener = document.createElement("button");
    document.body.appendChild(opener);
    opener.focus();
    const { unmount } = render(<NewRoomDialog bots={[SCOUT]} onClose={vi.fn()} onCreated={vi.fn()} />);
    const cancel = screen.getByRole("button", { name: "Cancel" });
    cancel.focus();
    await userEvent.tab();
    expect(screen.getByLabelText("Room name")).toHaveFocus();
    await userEvent.tab({ shift: true });
    expect(cancel).toHaveFocus();
    unmount();
    expect(opener).toHaveFocus();
    opener.remove();
  });
});
