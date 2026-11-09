import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import { FindAddPill } from "../src/components/workspace/FindAddPill";
import { ToastProvider } from "../src/ui/Toast";
import { makeQuickLine, makeTask } from "./taskFixtures";

const parseMock = vi.fn();
const createMock = vi.fn();
vi.mock("../src/api/tasks", () => ({
  parseQuickLine: (...a: unknown[]) => parseMock(...a),
  createTask: (...a: unknown[]) => createMock(...a),
}));

function Where() {
  return <output aria-label="Address">{useLocation().search}</output>;
}

function pill(start = "/board?tab=tasks", projectId?: string) {
  return render(
    <MemoryRouter initialEntries={[start]}>
      <ToastProvider>
        <FindAddPill projectId={projectId} />
        <Where />
      </ToastProvider>
    </MemoryRouter>,
  );
}

const box = () => screen.getByRole("combobox", { name: "Add or find anything" });
const address = () => screen.getByRole("status", { name: "Address" });

beforeEach(() => {
  parseMock.mockReset().mockImplementation(async ({ text }: { text: string }) =>
    makeQuickLine({ title: text.replace(" tomorrow", ""), ready: true }));
  createMock.mockReset().mockImplementation(async (input: { title: string }) => makeTask({ id: "new1", title: input.title }));
});
afterEach(cleanup);

describe("the Add or find anything pill", () => {
  it("shows its hint and puts what you type in the address as the search (?q=)", async () => {
    pill();
    expect(box()).toHaveAttribute("placeholder", "Add or find anything…");
    await userEvent.type(box(), "beans");
    await waitFor(() => expect(address()).toHaveTextContent("q=beans"));
  });

  it("shows the server's reading as chips while you type", async () => {
    parseMock.mockResolvedValue(makeQuickLine({ title: "Call Ana", ready: true, due_date: "2026-10-24", due_text: "Sat 24 Oct" } as never));
    pill();
    await userEvent.type(box(), "Call Ana tomorrow");
    await waitFor(() => expect(parseMock).toHaveBeenCalled());
    expect(await screen.findByText("Sat 24 Oct")).toBeInTheDocument();
  });

  it("adds the line as a task on Enter, through the server's reading, then clears the line and the search", async () => {
    pill("/board?tab=tasks", "p1");
    await userEvent.type(box(), "Sow the beans{Enter}");
    await waitFor(() => expect(createMock).toHaveBeenCalledWith(expect.objectContaining({ title: "Sow the beans" })));
    expect(parseMock).toHaveBeenLastCalledWith(expect.objectContaining({ text: "Sow the beans", project_id: "p1" }));
    expect(await screen.findByText("Added “Sow the beans”")).toBeInTheDocument();
    expect(box()).toHaveValue("");
    await waitFor(() => expect(address()).not.toHaveTextContent("q="));
  });

  it("says what to fix instead of adding when the reading is blocked", async () => {
    parseMock.mockResolvedValue(makeQuickLine({ title: "Paint", ready: false, project_question: "Which project is “Casa”?" }));
    pill();
    await userEvent.type(box(), "€20{Enter}");
    await waitFor(() => expect(parseMock).toHaveBeenCalled());
    expect(await screen.findByText("Which project is “Casa”?")).toBeInTheDocument();
    expect(createMock).not.toHaveBeenCalled();
  });

  it("says a failed add in words and keeps the line", async () => {
    createMock.mockRejectedValue(new Error("down"));
    pill();
    await userEvent.type(box(), "Ring Grandma{Enter}");
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(box()).toHaveValue("Ring Grandma");
  });
});
