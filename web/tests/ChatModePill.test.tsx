import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ChatModePill } from "../src/components/chat/ChatModePill";
import { makeBot } from "./fixtures";

const setApprovalMock = vi.fn();
vi.mock("../src/api/bots", () => ({ setApproval: (...args: unknown[]) => setApprovalMock(...args) }));
afterEach(() => { cleanup(); setApprovalMock.mockReset(); });

const linuxBot = (ask_topics: string[] = [], auto_review?: boolean) =>
  makeBot({ computer: "linux", approval: { mode: "auto_edit", ask_topics, locked_topics: ["posting"], auto_review } as never });

describe("the chat mode pill (owner decision 2026-10-25)", () => {
  it("names the current mode and lists the three with their lines, the current one checked", async () => {
    render(<ChatModePill bot={linuxBot([], true)} onChange={vi.fn()} onError={vi.fn()} />);
    const pill = screen.getByRole("button", { name: "Chat mode: Full auto" });
    expect(pill).toHaveTextContent("Full auto");
    await userEvent.click(pill);
    const items = screen.getAllByRole("menuitemradio");
    expect(items.map((item) => item.getAttribute("aria-checked"))).toEqual(["false", "false", "true"]);
    expect(items[0]).toHaveTextContent("Ask me");
    expect(items[0]).toHaveTextContent("Every click on its computer waits for your OK.");
    expect(items[1]).toHaveTextContent("Just browse");
    expect(items[1]).toHaveTextContent("Ordinary clicks just happen. Buttons it can't read still ask.");
    expect(items[2]).toHaveTextContent("Paying, sending, deleting, typing and new sites still ask.");
  });

  it("picking a mode saves it once and hands back the bot", async () => {
    const saved = linuxBot(["files", "browsing"]);
    setApprovalMock.mockResolvedValue(saved);
    const onChange = vi.fn();
    render(<ChatModePill bot={linuxBot(["files"])} onChange={onChange} onError={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: "Chat mode: Just browse" }));
    await userEvent.click(screen.getByRole("menuitemradio", { name: /Ask me/ }));
    expect(setApprovalMock).toHaveBeenCalledTimes(1);
    expect(setApprovalMock).toHaveBeenCalledWith("bot-1", "auto_edit", ["files", "browsing"], false);
    await vi.waitFor(() => expect(onChange).toHaveBeenCalledWith(saved));
  });

  it("picking the current mode saves nothing", async () => {
    render(<ChatModePill bot={linuxBot()} onChange={vi.fn()} onError={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: "Chat mode: Just browse" }));
    await userEvent.click(screen.getByRole("menuitemradio", { name: /Just browse/ }));
    expect(setApprovalMock).not.toHaveBeenCalled();
  });

  it("a failed save is said in words and the bot stays as it was", async () => {
    setApprovalMock.mockRejectedValue(new Error("boom"));
    const onChange = vi.fn();
    const onError = vi.fn();
    render(<ChatModePill bot={linuxBot()} onChange={onChange} onError={onError} />);
    await userEvent.click(screen.getByRole("button", { name: "Chat mode: Just browse" }));
    await userEvent.click(screen.getByRole("menuitemradio", { name: /Full auto/ }));
    await vi.waitFor(() => expect(onError).toHaveBeenCalledWith(expect.any(String)));
    expect(onChange).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Chat mode: Just browse" })).toBeInTheDocument();
  });
});
