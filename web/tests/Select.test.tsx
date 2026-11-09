import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { Field } from "../src/ui/Field";
import { Select } from "../src/ui/Select";

afterEach(() => cleanup());

type Priority = "low" | "medium" | "high";
const OPTIONS = [
  { value: "low" as const, label: "Low" }, { value: "medium" as const, label: "Medium" }, { value: "high" as const, label: "High" },
];

function Picker({ onChange = vi.fn() }: { onChange?: (value: Priority) => void }) {
  const [value, setValue] = useState<Priority>("medium");
  return (
    <Field label="Priority" hint="How soon it matters">
      <Select value={value} options={OPTIONS} onChange={(next) => { setValue(next); onChange(next); }} />
    </Field>
  );
}

describe("Select", () => {
  it("is a combobox named by its Field, showing the chosen option", () => {
    render(<Picker />);
    const select = screen.getByRole("combobox", { name: "Priority" });
    expect(select).toHaveTextContent("Medium");
    expect(select).toHaveAccessibleDescription("How soon it matters");
  });

  it("opens on a click and picks an option", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<Picker onChange={onChange} />);
    await user.click(screen.getByRole("combobox", { name: "Priority" }));
    await user.click(screen.getByRole("option", { name: "High" }));
    expect(onChange).toHaveBeenCalledWith("high");
    expect(screen.getByRole("combobox", { name: "Priority" })).toHaveTextContent("High");
  });

  it("works from the keyboard alone: open, arrows, Enter, and focus back on the trigger", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<Picker onChange={onChange} />);
    const select = screen.getByRole("combobox", { name: "Priority" });
    select.focus();
    await user.keyboard("{Enter}");
    expect(await screen.findByRole("listbox")).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Medium" })).toHaveFocus();
    await user.keyboard("{ArrowDown}");
    expect(screen.getByRole("option", { name: "High" })).toHaveFocus();
    await user.keyboard("{Enter}");
    expect(onChange).toHaveBeenCalledWith("high");
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
    expect(select).toHaveFocus();
  });

  it("Escape closes the list without changing the choice", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<Picker onChange={onChange} />);
    await user.click(screen.getByRole("combobox", { name: "Priority" }));
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
    expect(onChange).not.toHaveBeenCalled();
    expect(screen.getByRole("combobox", { name: "Priority" })).toHaveTextContent("Medium");
  });

  it("a select outside a Field takes its name from label", () => {
    render(<Select label="Lead bot" value="none" options={[{ value: "none", label: "No lead bot" }]} onChange={vi.fn()} />);
    expect(screen.getByRole("combobox", { name: "Lead bot" })).toHaveTextContent("No lead bot");
  });
});
