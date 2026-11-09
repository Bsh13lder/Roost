import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import { Board } from "../src/pages/Board";
import { ToastProvider } from "../src/ui/Toast";

vi.mock("../src/components/board/TasksArea", () => ({ TasksArea: () => <p>Tasks panel</p> }));
vi.mock("../src/components/board/MoneyBoard", () => ({ MoneyBoard: () => <p>Money panel</p> }));
vi.mock("../src/components/workspace/notes/NotesTree", () => ({
  default: ({ openNote, openDocument }: { openNote?: string | null; openDocument?: string | null }) => (
    <p>Notes tree{openNote ? ` note ${openNote}` : ""}{openDocument ? ` document ${openDocument}` : ""}</p>
  ),
}));
vi.mock("../src/components/workspace/calendar/WorkspaceCalendar", () => ({ default: () => <p>Calendar panel</p> }));
vi.mock("../src/components/workspace/FindAddPill", () => ({ FindAddPill: () => <input aria-label="Add or find anything" /> }));

function Where() {
  return <output aria-label="Address">{useLocation().search}</output>;
}

function board(start: string) {
  return render(
    <MemoryRouter initialEntries={[start]}>
      <ToastProvider><Board /><Where /></ToastProvider>
    </MemoryRouter>,
  );
}

const sections = () => screen.getByRole("group", { name: "Workspace sections" });
const address = () => screen.getByRole("status", { name: "Address" });

afterEach(cleanup);

describe("the Workspace", () => {
  it("opens on Tasks with Tasks · Notes · Calendar and the Add or find pill; Money is not a section", () => {
    board("/board");
    const buttons = Array.from(sections().querySelectorAll("button")).map((button) => button.textContent);
    expect(buttons).toEqual(["Tasks", "Notes", "Calendar"]);
    expect(screen.getByRole("button", { name: "Tasks" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText("Tasks panel")).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Add or find anything" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Money" })).toBeNull();
    expect(screen.getByRole("heading", { name: "Workspace" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to chats" })).toHaveAttribute("href", "/");
  });

  it("switches sections in the address", async () => {
    board("/board");
    await userEvent.click(screen.getByRole("button", { name: "Calendar" }));
    expect(await screen.findByText("Calendar panel")).toBeInTheDocument();
    expect(address()).toHaveTextContent("tab=calendar");
    await userEvent.click(screen.getByRole("button", { name: "Notes" }));
    expect(await screen.findByText("Notes tree")).toBeInTheDocument();
    expect(address()).toHaveTextContent("tab=notes");
  });

  it("opens the note or document an old link names", async () => {
    const first = board("/board?tab=notes&note=n1");
    expect(await screen.findByText("Notes tree note n1")).toBeInTheDocument();
    first.unmount();
    board("/board?tab=documents&document=d1");
    expect(await screen.findByText("Notes tree document d1")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Notes" })).toHaveAttribute("aria-pressed", "true");
  });

  it("shows All money for the old Money tab, with the way back to the Workspace", () => {
    board("/board?tab=money");
    expect(screen.getByText("Money panel")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "All money" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to the Workspace" })).toHaveAttribute("href", "/board?tab=tasks");
    expect(screen.queryByRole("group", { name: "Workspace sections" })).toBeNull();
  });

  it("the old Projects tab opens Tasks on All; the old calendar layout opens Calendar", async () => {
    const first = board("/board?tab=projects");
    await waitFor(() => expect(address()).toHaveTextContent("?tab=tasks&project=all"));
    first.unmount();
    board("/board?tab=tasks&layout=calendar");
    expect(await screen.findByText("Calendar panel")).toBeInTheDocument();
  });
});
