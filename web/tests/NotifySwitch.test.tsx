import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NotifySwitch } from "../src/components/profile/NotifySwitch";
import { makeBot } from "./fixtures";

const setNotifyMock = vi.fn();
vi.mock("../src/api/bots", () => ({ setNotify: (id: string, v: boolean) => setNotifyMock(id, v) }));

afterEach(() => { cleanup(); vi.unstubAllGlobals(); setNotifyMock.mockReset(); });

describe("NotifySwitch", () => {
  it("switches notifications off", async () => {
    setNotifyMock.mockResolvedValue(makeBot({ notify: false }));
    const onChange = vi.fn();
    render(<NotifySwitch bot={makeBot({ notify: true })} onChange={onChange} />);
    const toggle = screen.getByRole("switch", { name: "Notifications" });
    expect(toggle).toHaveAttribute("aria-checked", "true");
    await userEvent.click(toggle);
    expect(setNotifyMock).toHaveBeenCalledWith("bot-1", false);
  });

  it("asks the browser for permission when switching on", async () => {
    const requestPermission = vi.fn().mockResolvedValue("granted");
    vi.stubGlobal("Notification", Object.assign(function () {}, { permission: "default", requestPermission }));
    setNotifyMock.mockResolvedValue(makeBot({ notify: true }));
    render(<NotifySwitch bot={makeBot({ notify: false })} onChange={vi.fn()} />);
    await userEvent.click(screen.getByRole("switch"));
    expect(requestPermission).toHaveBeenCalled();
    expect(setNotifyMock).toHaveBeenCalledWith("bot-1", true);
  });

  it("a switch that is on by default offers the browser permission in one tap", async () => {
    const requestPermission = vi.fn().mockResolvedValue("granted");
    vi.stubGlobal("Notification", Object.assign(function () {}, { permission: "default", requestPermission }));
    render(<NotifySwitch bot={makeBot({ notify: true })} onChange={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: "Allow browser notifications" }));
    expect(requestPermission).toHaveBeenCalled();
    expect(setNotifyMock).not.toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: "Allow browser notifications" })).not.toBeInTheDocument();
  });
});
