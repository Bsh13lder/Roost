import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { MoneyEmpty, ProjectTasksEmpty, TasksEmpty } from "../src/components/board/BoardEmpty";
import { makeBot } from "./fixtures";

let bots = {};
vi.mock("../src/hooks/useLiveStore", () => ({ useLiveState: () => ({ bots, boardVersion: { tasks: 0, money: 0 } }) }));

const main = makeBot({ id: "bot-main", name: "Chief", is_primary: true });
const lead = makeBot({ id: "bot-lead", name: "Builder", is_primary: false });

function at(element: JSX.Element) {
  return render(
    <MemoryRouter initialEntries={["/board"]}>
      <Routes>
        <Route path="/board" element={element} />
        <Route path="/bots/:id" element={<p>Chat with a bot</p>} />
      </Routes>
    </MemoryRouter>,
  );
}
afterEach(() => cleanup());

describe("the Board's empty states (G14)", () => {
  it("Tasks empty shows the main bot and the first prompt", async () => {
    bots = { [main.id]: main, [lead.id]: lead };
    at(<TasksEmpty />);
    expect(screen.getByText("Nothing here. Nice.")).toBeInTheDocument();
    expect(screen.getByText("Add a task above, or ask Chief: “plan my week”.")).toBeInTheDocument();
    expect(document.querySelector(".empty-state__art svg")).not.toBeNull(); // the main bot's robot
    await userEvent.setup().click(screen.getByRole("button", { name: "Ask Chief" }));
    expect(await screen.findByText("Chat with a bot")).toBeInTheDocument();
  });

  it("Tasks empty still reads well with no bots yet", () => {
    bots = {};
    at(<TasksEmpty />);
    expect(screen.getByText("Nothing here. Nice.")).toBeInTheDocument();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("Money empty focuses the line", async () => {
    bots = { [main.id]: main };
    at(<div><input aria-label="New expense" /><MoneyEmpty /></div>);
    expect(screen.getByText("Nothing spent yet this month")).toBeInTheDocument();
    expect(screen.getByText("Type an expense in the line above, like “€12 lunch /Trip”.")).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: "Add an expense" }));
    expect(screen.getByLabelText("New expense")).toHaveFocus();
  });

  it("a project's empty tasks names its lead bot", () => {
    bots = { [main.id]: main, [lead.id]: lead };
    at(<ProjectTasksEmpty leadBotId="bot-lead" />);
    expect(screen.getByText("No tasks yet")).toBeInTheDocument();
    expect(screen.getByText("Add the first task, or ask Builder.")).toBeInTheDocument();
    cleanup();
    at(<ProjectTasksEmpty leadBotId={null} />);
    expect(screen.getByText("Add the first task, or ask Chief.")).toBeInTheDocument();
  });
});
