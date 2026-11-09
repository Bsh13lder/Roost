import { readFileSync } from "node:fs";
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { Tabs } from "../src/ui/Tabs";

afterEach(() => cleanup());

type Tab = "tasks" | "money" | "notes";
const TABS = [{ id: "tasks" as const, label: "Tasks" }, { id: "money" as const, label: "Money" }, { id: "notes" as const, label: "Notes" }];

function Board() {
  const [tab, setTab] = useState<Tab>("tasks");
  return <Tabs label="Board" tabs={TABS} value={tab} onChange={setTab} panelClassName="board-panel"><p>Panel {tab}</p></Tabs>;
}

describe("Tabs", () => {
  it("is a named tab list with the selected tab's panel, labelled by its tab", () => {
    render(<Board />);
    expect(screen.getByRole("tablist", { name: "Board" })).toBeInTheDocument();
    expect(screen.getAllByRole("tab").map((tab) => tab.textContent)).toEqual(["Tasks", "Money", "Notes"]);
    expect(screen.getByRole("tab", { name: "Tasks" })).toHaveAttribute("aria-selected", "true");
    const panel = screen.getByRole("tabpanel", { name: "Tasks" });
    expect(panel).toHaveTextContent("Panel tasks");
    expect(panel).toHaveClass("tabs__panel", "board-panel");
  });

  it("a click selects a tab", async () => {
    render(<Board />);
    await userEvent.click(screen.getByRole("tab", { name: "Notes" }));
    expect(screen.getByRole("tab", { name: "Notes" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tabpanel", { name: "Notes" })).toHaveTextContent("Panel notes");
  });

  it("arrow keys move between tabs and select them; Home and End jump to the ends", async () => {
    const user = userEvent.setup();
    render(<Board />);
    screen.getByRole("tab", { name: "Tasks" }).focus();
    await user.keyboard("{ArrowRight}");
    expect(screen.getByRole("tab", { name: "Money" })).toHaveFocus();
    expect(screen.getByRole("tab", { name: "Money" })).toHaveAttribute("aria-selected", "true");
    await user.keyboard("{End}");
    expect(screen.getByRole("tab", { name: "Notes" })).toHaveAttribute("aria-selected", "true");
    await user.keyboard("{Home}");
    expect(screen.getByRole("tab", { name: "Tasks" })).toHaveAttribute("aria-selected", "true");
  });

  it("draws a count and keeps it out of the accessible name", () => {
    render(<Tabs label="Board" variant="line" value="tasks" onChange={() => undefined}
      tabs={[{ id: "tasks", label: "Tasks", count: 4 }, { id: "money", label: "Money", count: 0 }]}><p>x</p></Tabs>);
    const tab = screen.getByRole("tab", { name: "Tasks" });
    expect(tab.querySelector(".tabs__count")).toHaveTextContent("4");
    expect(tab.querySelector(".tabs__count")).toHaveAttribute("aria-hidden", "true");
    expect(screen.getByRole("tab", { name: "Money" }).querySelector(".tabs__count")).toBeNull();
  });

  it("a danger count carries the danger class", () => {
    render(<Tabs label="Board" variant="line" value="tasks" onChange={() => undefined}
      tabs={[{ id: "tasks", label: "Tasks", count: 2, countTone: "danger" }]}><p>x</p></Tabs>);
    expect(document.querySelector(".tabs__count")).toHaveClass("tabs__count--danger");
  });

  it("the line variant marks the list for sideways scroll", () => {
    const { container } = render(<Tabs label="Board" variant="line" value="tasks" onChange={() => undefined}
      tabs={[{ id: "tasks", label: "Tasks" }]}><p>x</p></Tabs>);
    expect(container.querySelector(".tabs")).toHaveClass("tabs--line");
    const css = readFileSync("src/styles/ui-overlays.css", "utf8");
    expect(css).toMatch(/\.tabs--line \.tabs__list\s*\{[^}]*overflow-x: auto/);
  });

  it("the pill variant is unchanged", () => {
    const { container } = render(<Board />);
    expect(container.querySelector(".tabs")).not.toHaveClass("tabs--line");
    expect(container.querySelector(".tabs__count")).toBeNull();
  });
});
