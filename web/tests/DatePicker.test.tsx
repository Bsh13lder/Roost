import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { DatePicker } from "../src/ui/date/DatePicker";
import { PAST_PICKS } from "../src/ui/date/picks";
import { resolveDay } from "../src/ui/date/resolve";

const parseDateMock = vi.fn();
vi.mock("../src/api/dates", () => ({ parseDate: (text: string, kind?: string) => parseDateMock(text, kind) }));

beforeEach(() => {
  parseDateMock.mockReset();
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2026-10-15T10:00:00Z"));
});
afterEach(() => { cleanup(); vi.useRealTimers(); });

function Day({ onChange = vi.fn(), past = false }: { onChange?: (value: string) => void; past?: boolean }) {
  const [value, setValue] = useState("");
  return (
    <DatePicker label="Day" value={value} picks={past ? PAST_PICKS : undefined} max={past ? "2026-10-15" : undefined}
      onChange={(next) => { setValue(next); onChange(next); }} />
  );
}

describe("DatePicker", () => {
  it("offers Today, Tomorrow, Next week and No date, and has no time chips", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<Day onChange={onChange} />);
    await user.click(screen.getByRole("button", { name: "Open calendar" }));
    const panel = screen.getByRole("dialog", { name: "Pick a day" });
    expect(panel).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "Time" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Tomorrow" }));
    expect(onChange).toHaveBeenLastCalledWith("2026-10-16");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByText("Fri 16 Oct 2026")).toBeInTheDocument();
  });

  it("a day that names a time shows only the day", async () => {
    parseDateMock.mockResolvedValue({ due_date: "2026-10-16T09:00:00+02:00" });
    const user = userEvent.setup();
    render(<Day />);
    await user.type(screen.getByRole("textbox", { name: "Day" }), "tomorrow at 9");
    expect(await screen.findByText("Fri 16 Oct 2026")).toBeInTheDocument();
  });

  it("an expense's day looks back, and the calendar offers nothing after today", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<Day past onChange={onChange} />);
    await user.click(screen.getByRole("button", { name: "Open calendar" }));
    expect(screen.queryByRole("button", { name: "No date" })).not.toBeInTheDocument();
    expect(await screen.findByRole("button", { name: /October 16th, 2026/ })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Yesterday" }));
    expect(onChange).toHaveBeenLastCalledWith("2026-10-14");
  });
});

describe("DatePicker's reading kind", () => {
  it("has the gateway read typed words as a task's due unless told they are an expense's day", async () => {
    parseDateMock.mockResolvedValue({ due_date: "2026-10-16" });
    const { unmount } = render(<DatePicker label="Starts" value="tomorrow" onChange={vi.fn()} />);
    await vi.waitFor(() => expect(parseDateMock).toHaveBeenLastCalledWith("tomorrow", "due"));
    unmount();
    render(<DatePicker label="Day" value="yesterday" kind="spent" onChange={vi.fn()} />);
    await vi.waitFor(() => expect(parseDateMock).toHaveBeenLastCalledWith("yesterday", "spent"));
  });
});

describe("resolveDay", () => {
  it("keeps a picked day, empties an empty field, and has the gateway read words", async () => {
    expect(await resolveDay("2026-10-20")).toBe("2026-10-20");
    expect(await resolveDay("  ")).toBeNull();
    parseDateMock.mockResolvedValue({ due_date: "2026-10-19T09:00:00+02:00" });
    expect(await resolveDay("next monday at 9")).toBe("2026-10-19");
    expect(parseDateMock).toHaveBeenCalledTimes(1);
    expect(parseDateMock).toHaveBeenLastCalledWith("next monday at 9", "due");
  });

  it("reads an expense's words with the expense's reading", async () => {
    parseDateMock.mockResolvedValue({ due_date: "2026-10-12" });
    expect(await resolveDay("hace 3 días", "spent")).toBe("2026-10-12");
    expect(parseDateMock).toHaveBeenLastCalledWith("hace 3 días", "spent");
  });
});
