import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TaskActivity } from "../src/components/tasks/TaskActivity";
import { makeBot } from "./fixtures";
import { makeTask } from "./taskFixtures";

const keepTaskMock = vi.fn();
vi.mock("../src/api/tasks", () => ({ keepTask: (...a: unknown[]) => keepTaskMock(...a) }));
vi.mock("../src/hooks/useLiveStore", () => ({ useLiveState: () => ({ bots: { "bot-1": makeBot({ id: "bot-1", name: "Helper" }) } }) }));

const onChanged = vi.fn();
beforeEach(() => { keepTaskMock.mockReset().mockResolvedValue(makeTask()); onChanged.mockReset(); });
afterEach(() => cleanup());

describe("the drawer's activity (redesign P3)", () => {
  it("says which bot made it and when, when it changed, and when it ended", () => {
    render(<TaskActivity task={makeTask({ created_by_bot: "bot-1", status: "done", completed_at: "2026-10-15T16:05:00+00:00",
      updated_at: "2026-10-15T16:05:00+00:00" })} onChanged={onChanged} />);
    expect(screen.getByText("Made by Helper, Wed 14 Oct, 10:00")).toBeInTheDocument();
    expect(screen.getByText("Last changed Thu 15 Oct, 18:05")).toBeInTheDocument();
    expect(screen.getByText("Done Thu 15 Oct, 18:05")).toBeInTheDocument();
  });

  it("names no maker it cannot know, and a retired bot as such", () => {
    const { rerender } = render(<TaskActivity task={makeTask()} onChanged={onChanged} />);
    expect(screen.getByText(/^Made by you, or by a bot since retired, /)).toBeInTheDocument();
    rerender(<TaskActivity task={makeTask({ created_by_bot: "bot-gone" })} onChanged={onChanged} />);
    expect(screen.getByText(/^Made by a retired bot, /)).toBeInTheDocument();
  });

  it("marks a web-made task, and Keep vouches for it", async () => {
    const user = userEvent.setup();
    render(<TaskActivity task={makeTask({ tainted: true })} onChanged={onChanged} />);
    expect(screen.getByText("from web content")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Keep Fix the sink as yours" }));
    expect(keepTaskMock).toHaveBeenCalledWith("t1");
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
  });
});
