import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QuestionBook } from "../src/components/questions/QuestionBook";
import type { QuestionOut } from "../src/api/questions";

const api = { listQuestions: vi.fn(), answerQuestion: vi.fn(), dismissQuestion: vi.fn() };
vi.mock("../src/api/questions", () => ({
  listQuestions: (...a: unknown[]) => api.listQuestions(...a), answerQuestion: (...a: unknown[]) => api.answerQuestion(...a),
  dismissQuestion: (...a: unknown[]) => api.dismissQuestion(...a),
}));
vi.mock("../src/hooks/useLiveStore", () => ({ useLiveState: () => ({ routineVersion: { questions: 0 } }) }));

const question = (over: Partial<QuestionOut> = {}): QuestionOut => ({
  id: "q-1", bot_id: "bot-1", routine_id: "r-1", question: "Weekly or daily digest?", default_choice: "weekly",
  why: "You never said", answer: null, tainted: false, state: "open", created_at: "2026-10-21T08:00:00Z", answered_at: null, ...over,
});
beforeEach(() => { api.listQuestions.mockResolvedValue([question()]); });
afterEach(() => { cleanup(); Object.values(api).forEach((mock) => mock.mockReset()); });

describe("QuestionBook", () => {
  it("lists open questions with their default", async () => {
    render(<QuestionBook botId="bot-1" />);
    expect(await screen.findByText("Weekly or daily digest?")).toBeInTheDocument();
    expect(screen.getByText("Carrying on with: weekly")).toBeInTheDocument();
    expect(screen.getByText("You never said")).toBeInTheDocument();
    expect(api.listQuestions).toHaveBeenCalledWith("bot-1");
  });

  it("answering posts and the question leaves the book", async () => {
    api.answerQuestion.mockResolvedValue(question({ state: "answered" }));
    render(<QuestionBook botId="bot-1" />);
    await userEvent.type(await screen.findByLabelText("Your answer to: Weekly or daily digest?"), "Daily");
    await userEvent.click(screen.getByRole("button", { name: "Answer" }));
    expect(api.answerQuestion).toHaveBeenCalledWith("q-1", "Daily");
    await waitFor(() => expect(screen.queryByText("Weekly or daily digest?")).not.toBeInTheDocument());
  });

  it("will not send an empty answer", async () => {
    render(<QuestionBook botId="bot-1" />);
    await screen.findByText("Weekly or daily digest?");
    expect(screen.getByRole("button", { name: "Answer" })).toBeDisabled();
  });

  it("dismiss closes it with no message", async () => {
    api.dismissQuestion.mockResolvedValue(question({ state: "dismissed" }));
    render(<QuestionBook botId="bot-1" />);
    await userEvent.click(await screen.findByRole("button", { name: "Dismiss" }));
    expect(api.dismissQuestion).toHaveBeenCalledWith("q-1");
    await waitFor(() => expect(screen.queryByText("Weekly or daily digest?")).not.toBeInTheDocument());
  });

  it("marks a question noted from web content", async () => {
    api.listQuestions.mockResolvedValue([question({ tainted: true })]);
    render(<QuestionBook botId="bot-1" />);
    expect(await screen.findByText("from web content")).toBeInTheDocument();
  });
});
