import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ApiError } from "../src/api/client";
import { RoutineFinishedRow } from "../src/components/chat/RoutineFinishedRow";
import { finishedLine } from "../src/components/routines/lastError";
import { makeMessage } from "./fixtures";

// Plain functions, not spies: a spy that returns a rejected promise makes vitest report an unhandled rejection.
const api = vi.hoisted(() => ({
  calls: [] as string[],
  resume: (_id: string): Promise<unknown> => Promise.resolve({}),
  remove: (_id: string): Promise<void> => Promise.resolve(),
}));
vi.mock("../src/api/routines", () => ({
  resumeRoutine: (id: string) => { api.calls.push(`resume ${id}`); return api.resume(id); },
  deleteRoutine: (id: string) => { api.calls.push(`delete ${id}`); return api.remove(id); },
}));

const TEXT = "Finished routine · Watch physio: The appointment is booked. I'll delete it in 7 days.";
const BODY = JSON.stringify({
  routine_id: "r-1", name: "Watch physio", reason: "The appointment is booked", delete_at: "2026-11-18T08:00:00+00:00", text: TEXT,
});
const line = (body: string, tainted = false) => makeMessage({ role: "activity", kind: "routine_finished", body, tainted });
const renderLine = (message = line(BODY)) => render(<ul><RoutineFinishedRow message={message} /></ul>);

beforeEach(() => { api.calls.length = 0; api.resume = () => Promise.resolve({}); api.remove = () => Promise.resolve(); });
afterEach(() => cleanup());

describe("RoutineFinishedRow", () => {
  it("shows the server's line with Resume and Delete now", () => {
    renderLine();
    expect(screen.getByText(TEXT)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Resume routine Watch physio" })).toHaveTextContent("Resume");
    expect(screen.getByRole("button", { name: "Delete routine Watch physio now" })).toHaveTextContent("Delete now");
    expect(screen.queryByText(/web content/i)).not.toBeInTheDocument();
  });

  it("a line from a tainted run wears the web mark", () => {
    renderLine(line(BODY, true));
    expect(screen.getByText(TEXT).parentElement?.querySelector(".message__taint")).not.toBeNull();
  });

  it("Resume resumes the routine and the line says so", async () => {
    renderLine();
    await userEvent.click(screen.getByRole("button", { name: /Resume/ }));
    expect(api.calls).toEqual(["resume r-1"]);
    expect(await screen.findByText("Resumed routine · Watch physio")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("Delete now deletes it at once", async () => {
    renderLine();
    await userEvent.click(screen.getByRole("button", { name: /Delete routine/ }));
    expect(api.calls).toEqual(["delete r-1"]);
    expect(await screen.findByText("Deleted routine · Watch physio")).toBeInTheDocument();
  });

  it("a routine already gone says so, and another failure keeps the buttons", async () => {
    api.resume = () => Promise.reject(new ApiError(404, "Routine not found"));
    renderLine();
    await userEvent.click(screen.getByRole("button", { name: /Resume/ }));
    expect(await screen.findByText("That routine is already gone.")).toBeInTheDocument();
    cleanup();
    api.remove = () => Promise.reject(new ApiError(500, "Could not delete it."));
    renderLine();
    await userEvent.click(screen.getByRole("button", { name: /Delete routine/ }));
    expect(await screen.findByText(/Could not delete it\./)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Resume/ })).toBeInTheDocument();
  });

  it("a body that isn't a finished line shows as plain text", () => {
    renderLine(line("not json"));
    expect(screen.getByText("not json")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});

describe("finishedLine", () => {
  it("says the reason and the delete date, and nothing for a routine that is not finished", () => {
    expect(finishedLine({ at: "2026-11-11T08:00:00+00:00", reason: "booked", delete_at: "2026-11-18T08:00:00+00:00" }))
      .toMatch(/^Finished: booked · deleted \w{3} 18 Nov \d\d:\d\d$/);
    expect(finishedLine({ at: "2026-11-11T08:00:00+00:00", reason: "", delete_at: "bad" })).toBe("Finished");
    expect(finishedLine(null)).toBe("");
  });
});
