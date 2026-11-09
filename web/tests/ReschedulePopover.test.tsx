import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ReschedulePopover } from "../src/components/board/ReschedulePopover";

vi.mock("../src/ui/date/Calendar", () => ({
  default: ({ onSelect }: { onSelect: (day: string) => void }) => <button onClick={() => onSelect("2026-11-03")}>Pick 3 Nov</button>,
}));

beforeEach(() => { vi.useFakeTimers({ toFake: ["Date"] }); vi.setSystemTime(new Date("2026-10-20T10:00:00+02:00")); });
afterEach(() => { cleanup(); vi.useRealTimers(); });

async function open(onPick = vi.fn(), current: { day: string | null; time: string | null } | null = null) {
  render(<ReschedulePopover title="Reschedule “Pay the deposit”" current={current} onPick={onPick}
    trigger={<button type="button">Move</button>} />);
  await userEvent.click(screen.getByRole("button", { name: "Move" }));
  return onPick;
}

describe("ReschedulePopover", () => {
  it("a quick pick applies at once with its day", async () => {
    const onPick = await open();
    expect(screen.getByText("Reschedule “Pay the deposit”")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Tomorrow/ })).toHaveTextContent("Wed 21");
    await userEvent.click(screen.getByRole("button", { name: /Tomorrow/ }));
    expect(onPick).toHaveBeenCalledWith({ day: "2026-10-21", time: null });
    expect(screen.queryByText("Reschedule “Pay the deposit”")).toBeNull();
  });

  it("a calendar day applies at once, with the typed time", async () => {
    const onPick = await open();
    await userEvent.type(screen.getByLabelText("Time (optional)"), "09:30");
    await userEvent.click(await screen.findByRole("button", { name: "Pick 3 Nov" }));
    expect(onPick).toHaveBeenCalledWith({ day: "2026-11-03", time: "09:30" });
  });

  it("a bad time is refused in words and nothing applies", async () => {
    const onPick = await open();
    await userEvent.type(screen.getByLabelText("Time (optional)"), "25:99");
    await userEvent.click(screen.getByRole("button", { name: /Today/ }));
    expect(onPick).not.toHaveBeenCalled();
    expect(screen.getByText("Use a time like 09:30")).toBeInTheDocument();
  });

  it("No date clears the time too", async () => {
    const onPick = await open();
    await userEvent.type(screen.getByLabelText("Time (optional)"), "09:30");
    await userEvent.click(screen.getByRole("button", { name: "No date" }));
    expect(onPick).toHaveBeenCalledWith({ day: null, time: null });
  });

  it("Escape closes without a change", async () => {
    const onPick = await open();
    await userEvent.keyboard("{Escape}");
    expect(onPick).not.toHaveBeenCalled();
    expect(screen.queryByText("Reschedule “Pay the deposit”")).toBeNull();
  });
});
