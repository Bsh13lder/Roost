import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { Badge } from "../src/ui/Badge";
import { Button } from "../src/ui/Button";
import { Chip } from "../src/ui/Chip";
import { EmptyState } from "../src/ui/EmptyState";
import { Field } from "../src/ui/Field";
import { IconButton } from "../src/ui/IconButton";
import { Input } from "../src/ui/Input";
import { Meter } from "../src/ui/Meter";
import { Skeleton } from "../src/ui/Skeleton";
import { Textarea, fitHeight } from "../src/ui/Textarea";
import { PlusIcon } from "../src/components/icons";

afterEach(() => cleanup());

describe("Button and IconButton", () => {
  it("draws its variant and size, is a plain button by default, and is busy while loading", async () => {
    const onClick = vi.fn();
    const { rerender } = render(<Button variant="primary" size="sm" onClick={onClick}>Save</Button>);
    const button = screen.getByRole("button", { name: "Save" });
    expect(button).toHaveClass("btn", "btn--primary", "btn--sm");
    expect(button).toHaveAttribute("type", "button");
    await userEvent.click(button);
    expect(onClick).toHaveBeenCalledTimes(1);
    rerender(<Button variant="primary" loading onClick={onClick}>Save</Button>);
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Save" })).toHaveAttribute("aria-busy", "true");
  });

  it("an icon button is named by its label and can be a toggle", () => {
    render(<IconButton label="Search" icon={<PlusIcon />} pressed={false} />);
    const button = screen.getByRole("button", { name: "Search" });
    expect(button).toHaveClass("icon-btn", "icon-btn--md", "icon-btn--ghost");
    expect(button).toHaveAttribute("aria-pressed", "false");
  });
});

describe("Field, Input and Textarea", () => {
  it("labels its control and wires the hint and the error to it", () => {
    render(<Field label="Title" hint="Short is best" error="A task needs a title." optional><Input value="" onChange={vi.fn()} /></Field>);
    const box = screen.getByLabelText("Title");
    expect(box).toHaveAccessibleDescription("Short is best A task needs a title.");
    expect(box).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByRole("alert")).toHaveTextContent("A task needs a title.");
    expect(screen.getByText("optional")).toBeInTheDocument();
  });

  it("an input outside a Field keeps its own id and name", () => {
    render(<Input id="own" aria-label="Search notes" />);
    expect(screen.getByRole("textbox", { name: "Search notes" })).toHaveAttribute("id", "own");
  });

  it("a textarea grows with its text up to its cap, then scrolls", () => {
    const box = document.createElement("textarea");
    document.body.appendChild(box);
    box.style.lineHeight = "20px";
    box.style.padding = "0";
    Object.defineProperty(box, "scrollHeight", { configurable: true, get: () => 64 });
    fitHeight(box, 12);
    expect(box.style.height).toBe("64px");
    expect(box.style.overflowY).toBe("hidden");
    Object.defineProperty(box, "scrollHeight", { configurable: true, get: () => 900 });
    fitHeight(box, 12);
    expect(box.style.height).toBe("240px");
    expect(box.style.overflowY).toBe("auto");
    box.remove();
  });

  it("a textarea resizes when its value changes", async () => {
    function Grows() {
      const [text, setText] = useState("");
      return <Field label="Instructions"><Textarea value={text} onChange={(event) => setText(event.target.value)} /></Field>;
    }
    render(<Grows />);
    const box = screen.getByLabelText("Instructions");
    Object.defineProperty(box, "scrollHeight", { configurable: true, get: () => 48 });
    await userEvent.type(box, "a");
    expect(box).toHaveStyle({ height: "48px" });
    expect(box).toHaveClass("input--grow");
  });
});

describe("Chip, Badge, Meter, Skeleton and EmptyState", () => {
  it("a chip is a pressable pill", () => {
    render(<Chip selected>Tomorrow</Chip>);
    expect(screen.getByRole("button", { name: "Tomorrow" })).toHaveAttribute("aria-pressed", "true");
  });

  it("a badge carries its tone", () => {
    render(<Badge tone="warn">2 left</Badge>);
    expect(screen.getByText("2 left")).toHaveClass("badge", "badge--warn");
  });

  it("a meter clamps what it draws and announces, and says its value text", () => {
    render(<Meter label="This month" value={250} tone="over" valueText="Over by €150.00" />);
    const meter = screen.getByRole("meter", { name: "This month" });
    expect(meter).toHaveAttribute("aria-valuenow", "100");
    expect(meter).toHaveAttribute("aria-valuetext", "Over by €150.00");
    expect(meter.querySelector(".meter__fill--over")).toHaveStyle({ width: "100%" });
  });

  it("a skeleton is one loading status with hidden bars", () => {
    render(<Skeleton lines={3} label="Loading tasks" />);
    const status = screen.getByRole("status", { name: "Loading tasks" });
    expect(status.querySelectorAll(".skeleton")).toHaveLength(3);
  });

  it("an empty state shows its title, hint and action", () => {
    render(<EmptyState title="No notes yet" hint="Write one, or ask a bot." action={<Button>New note</Button>} />);
    expect(screen.getByText("No notes yet")).toBeInTheDocument();
    expect(screen.getByText("Write one, or ask a bot.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "New note" })).toBeInTheDocument();
  });
});
