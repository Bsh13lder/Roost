import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PlanKanban } from "../src/components/plan/PlanKanban";
import { item, plan } from "./planFixtures";

afterEach(cleanup);

function dataTransfer() {
  const store = new Map<string, string>();
  return { setData: (k: string, v: string) => store.set(k, v), getData: (k: string) => store.get(k) ?? "", effectAllowed: "", dropEffect: "" };
}
const column = (name: string) => screen.getByRole("region", { name });
const card = (text: string) => screen.getByText(text).closest(".kcard") as HTMLElement;

describe("PlanKanban", () => {
  it("shows Planned, On it and Done, each with its cards", () => {
    render(<PlanKanban items={plan().items} onMove={vi.fn()} />);
    expect(within(column("Planned")).getByText("Call the plumber")).toBeInTheDocument();
    expect(within(column("On it")).getByText("Write the report")).toBeInTheDocument();
    expect(within(column("Done")).getByText("Pay rent")).toBeInTheDocument();
  });

  it("drag moves a card and sends the item's id", () => {
    const onMove = vi.fn();
    render(<PlanKanban items={plan().items} onMove={onMove} />);
    const transfer = dataTransfer();
    fireEvent.dragStart(card("Call the plumber"), { dataTransfer: transfer });
    fireEvent.dragOver(column("Done"), { dataTransfer: transfer });
    fireEvent.drop(column("Done"), { dataTransfer: transfer });
    expect(onMove).toHaveBeenCalledWith("i-1", "done");
  });

  it("move to works from the keyboard", async () => {
    const onMove = vi.fn();
    render(<PlanKanban items={plan().items} onMove={onMove} />);
    await userEvent.click(screen.getByRole("button", { name: "More for Call the plumber" }));
    await userEvent.click(await screen.findByRole("menuitem", { name: "On it" }));
    expect(onMove).toHaveBeenCalledWith("i-1", "on_it");
  });

  it("dropped hides behind the toggle", async () => {
    render(<PlanKanban items={plan().items} onMove={vi.fn()} />);
    expect(screen.queryByText("Old idea")).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Dropped" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("switch", { name: "Show dropped" }));
    expect(within(column("Dropped")).getByText("Old idea")).toBeInTheDocument();
  });

  it("an item with no id cannot be moved", async () => {
    render(<PlanKanban items={[item({ id: null, text: "Loose line" })]} onMove={vi.fn()} />);
    expect(card("Loose line")).not.toHaveAttribute("draggable", "true");
    expect(screen.queryByRole("button", { name: "More for Loose line" })).not.toBeInTheDocument();
  });

  it("marks an item that came from web content and shows tags", () => {
    render(<PlanKanban items={[item({ tainted: true, tags: ["home"] })]} onMove={vi.fn()} />);
    expect(screen.getByText("from web content")).toBeInTheDocument();
    expect(screen.getByText("#home")).toBeInTheDocument();
  });
});
