import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { Field } from "../src/ui/Field";
import { DateTimePicker } from "../src/ui/date/DateTimePicker";

const parseDateMock = vi.fn();
vi.mock("../src/api/dates", () => ({ parseDate: (text: string) => parseDateMock(text) }));

// A browser far from Madrid, late in its evening: 22:30 UTC on 15 Oct 2026 is already the 16th in Madrid.
const NOW = new Date("2026-10-15T22:30:00Z");
let savedZone: string | undefined;
beforeAll(() => { savedZone = process.env.TZ; process.env.TZ = "America/Los_Angeles"; });
afterAll(() => { process.env.TZ = savedZone; });
beforeEach(() => {
  parseDateMock.mockReset();
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(NOW);
});
afterEach(() => { cleanup(); vi.useRealTimers(); });

function Due({ initial = "", onChange = vi.fn() }: { initial?: string; onChange?: (value: string) => void }) {
  const [value, setValue] = useState(initial);
  return (
    <Field label="Due">
      <DateTimePicker value={value} onChange={(next) => { setValue(next); onChange(next); }} />
    </Field>
  );
}

async function openCalendar(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("button", { name: "Open calendar" }));
  return screen.getByRole("dialog", { name: "Pick a day and a time" });
}

describe("DateTimePicker", () => {
  it("sends Madrid's day and Madrid wall time from a browser in Los Angeles, never a UTC instant", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<Due onChange={onChange} />);
    await openCalendar(user);
    await user.click(screen.getByRole("button", { name: "Tomorrow" }));
    expect(onChange).toHaveBeenLastCalledWith("2026-10-17"); // Madrid's tomorrow; the browser's would be the 16th
    await user.click(screen.getByRole("button", { name: "09:00" }));
    expect(onChange).toHaveBeenLastCalledWith("2026-10-17 09:00");
    expect(onChange.mock.calls.flat().some((value: string) => /Z$|[+-]\d{2}:\d{2}$/.test(value))).toBe(false);
    expect(screen.getByLabelText("Due")).toHaveValue("2026-10-17 09:00");
    expect(screen.getByText("Sat 17 Oct 2026, 09:00")).toBeInTheDocument();
    expect(parseDateMock).not.toHaveBeenCalled(); // a picked value needs no gateway
  });

  it("shows a stored due at its Madrid wall time", () => {
    render(<Due initial="2026-10-14 23:30" />);
    expect(screen.getByLabelText("Due")).toHaveValue("2026-10-14 23:30");
    expect(screen.getByText("Wed 14 Oct 2026, 23:30")).toBeInTheDocument();
  });

  it("a new day keeps the time already chosen, and No time drops it", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<Due initial="2026-10-20 15:00" onChange={onChange} />);
    await openCalendar(user);
    await user.click(screen.getByRole("button", { name: "Next week" }));
    expect(onChange).toHaveBeenLastCalledWith("2026-10-19 15:00");
    await user.click(screen.getByRole("button", { name: "No time" }));
    expect(onChange).toHaveBeenLastCalledWith("2026-10-19");
  });

  it("No date empties it", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<Due initial="2026-10-20" onChange={onChange} />);
    await openCalendar(user);
    await user.click(screen.getByRole("button", { name: "No date" }));
    expect(onChange).toHaveBeenLastCalledWith("");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("typed words go out as typed, and the line under says how the gateway reads them", async () => {
    parseDateMock.mockResolvedValue({ due_date: "2026-10-17T09:00:00+02:00" });
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<Due onChange={onChange} />);
    await user.type(screen.getByLabelText("Due"), "tomorrow at 9");
    expect(onChange).toHaveBeenLastCalledWith("tomorrow at 9");
    expect(await screen.findByText("Sat 17 Oct 2026, 09:00")).toBeInTheDocument();
    expect(parseDateMock).toHaveBeenLastCalledWith("tomorrow at 9");
  });

  it("says why words can't be read, and marks the box", async () => {
    const { ApiError } = await import("../src/api/client");
    parseDateMock.mockRejectedValue(new ApiError(422, "I could not read a date in “someday”. Try “tomorrow at 9” or 2026-10-20."));
    const user = userEvent.setup();
    render(<Due />);
    await user.type(screen.getByLabelText("Due"), "someday");
    expect(await screen.findByText(/I could not read a date in “someday”/)).toBeInTheDocument();
    expect(screen.getByLabelText("Due")).toHaveAttribute("aria-invalid", "true");
  });

  it("picks a day on the lazy calendar", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<Due onChange={onChange} />);
    await openCalendar(user);
    await user.click(await screen.findByRole("button", { name: /October 20th, 2026/ }));
    expect(onChange).toHaveBeenLastCalledWith("2026-10-20");
  });

  it("works from the keyboard alone: open, reach the grid, arrows, Enter, and focus back on the button", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<Due initial="2026-10-20" onChange={onChange} />);
    const opener = screen.getByRole("button", { name: "Open calendar" });
    await user.tab(); // the text box
    await user.tab();
    expect(opener).toHaveFocus();
    await user.keyboard("{Enter}");
    const panel = screen.getByRole("dialog", { name: "Pick a day and a time" });
    const selected = await screen.findByRole("button", { name: /October 20th, 2026/ });
    expect(panel).toContainElement(selected);
    expect(within(panel).getByRole("button", { name: "Today" })).toHaveFocus(); // focus moves into the panel
    // Tab walks the quick picks, the month arrows, then the grid's one tab stop: the chosen day.
    for (let step = 0; step < 6; step += 1) await user.tab();
    expect(selected).toHaveFocus();
    await user.keyboard("{ArrowRight}{ArrowDown}");
    expect(screen.getByRole("button", { name: /October 28th, 2026/ })).toHaveFocus();
    await user.keyboard("{Enter}");
    expect(onChange).toHaveBeenLastCalledWith("2026-10-28");
    expect(screen.getByRole("dialog")).toBeInTheDocument(); // a due still wants its time
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(opener).toHaveFocus();
  });

  it("hands text with a zone to the gateway to put on Madrid's clock, and never reads it as wall time", async () => {
    parseDateMock.mockResolvedValue({ due_date: "2026-10-16T11:00:00+02:00" });
    const user = userEvent.setup();
    render(<Due />);
    await user.type(screen.getByLabelText("Due"), "2026-10-16T09:00:00Z");
    expect(await screen.findByText("Fri 16 Oct 2026, 11:00")).toBeInTheDocument(); // 09:00 UTC is 11:00 in Madrid
    expect(screen.queryByText("Fri 16 Oct 2026, 09:00")).not.toBeInTheDocument();
    expect(parseDateMock).toHaveBeenLastCalledWith("2026-10-16T09:00:00Z");
  });

  it("does not preview a clock that does not exist: the gateway reads it", async () => {
    const { ApiError } = await import("../src/api/client");
    parseDateMock.mockRejectedValue(new ApiError(422, "I could not read a date in “2026-10-16 25:99”."));
    render(<Due initial="2026-10-16 25:99" />);
    expect(await screen.findByText(/I could not read a date in “2026-10-16 25:99”/)).toBeInTheDocument();
    expect(parseDateMock).toHaveBeenLastCalledWith("2026-10-16 25:99");
    expect(screen.getByLabelText("Due")).toHaveAttribute("aria-invalid", "true");
  });

  it("shows the day the gateway reads 24:00 as, not the day before", async () => {
    parseDateMock.mockResolvedValue({ due_date: "2026-10-17T00:00:00+02:00" });
    render(<Due initial="2026-10-16 24:00" />);
    expect(await screen.findByText("Sat 17 Oct 2026, 00:00")).toBeInTheDocument();
  });

  it("moves the grid to the month of a quick pick, and the arrows still turn the page", async () => {
    vi.setSystemTime(new Date("2026-10-29T10:00:00Z"));
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<Due initial="2026-10-29" onChange={onChange} />);
    await openCalendar(user);
    expect(await screen.findByRole("button", { name: /October 29th, 2026/ })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Next week" })); // Monday 2 November
    expect(onChange).toHaveBeenLastCalledWith("2026-11-02");
    expect(await screen.findByRole("button", { name: /November 2nd, 2026/ })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /previous month/i }));
    expect(await screen.findByRole("button", { name: /October 29th, 2026/ })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /previous month/i }));
    expect(await screen.findByRole("button", { name: /September 29th, 2026/ })).toBeInTheDocument();
  });
});
