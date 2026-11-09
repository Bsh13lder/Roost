import { beforeEach, describe, expect, it, vi } from "vitest";

const apiRequestMock = vi.fn();
vi.mock("../src/api/client", () => ({ apiRequest: (...args: unknown[]) => apiRequestMock(...args) }));
import { addStep, deleteStep, getTask, getTaskCounts, listTasks, moveStep, parseQuickLine, updateStep } from "../src/api/tasks";
import { addComment, deleteComment, editComment, listComments } from "../src/api/comments";

beforeEach(() => apiRequestMock.mockReset().mockResolvedValue({}));

describe("the task drawer's requests (redesign P3)", () => {
  it("reads one task, and changes its steps by id, ids escaped", async () => {
    await getTask("t 1");
    expect(apiRequestMock).toHaveBeenLastCalledWith("GET", "/api/tasks/t%201");
    await addStep("t1", "Buy a washer");
    expect(apiRequestMock).toHaveBeenLastCalledWith("POST", "/api/tasks/t1/steps", { title: "Buy a washer" });
    await updateStep("t1", "s/1", { done: true });
    expect(apiRequestMock).toHaveBeenLastCalledWith("PATCH", "/api/tasks/t1/steps/s%2F1", { done: true });
    await moveStep("t1", "s-1", 0);
    expect(apiRequestMock).toHaveBeenLastCalledWith("POST", "/api/tasks/t1/steps/s-1/move", { position: 0 });
    await deleteStep("t1", "s-1");
    expect(apiRequestMock).toHaveBeenLastCalledWith("DELETE", "/api/tasks/t1/steps/s-1");
  });

  it("reads a quick-add line, with a project page's project and the removed chips", async () => {
    await parseQuickLine({ text: "Call plumber /Home", project_id: "p1", skip: ["date"] });
    expect(apiRequestMock).toHaveBeenLastCalledWith("POST", "/api/tasks/parse",
      { text: "Call plumber /Home", project_id: "p1", skip: ["date"] });
  });

  it("reads and writes a task's comments", async () => {
    await listComments("t1");
    expect(apiRequestMock).toHaveBeenLastCalledWith("GET", "/api/tasks/t1/comments");
    await addComment("t1", { body: "15 mm", step_id: "s-1" });
    expect(apiRequestMock).toHaveBeenLastCalledWith("POST", "/api/tasks/t1/comments", { body: "15 mm", step_id: "s-1" });
    await editComment("c1", "16 mm");
    expect(apiRequestMock).toHaveBeenLastCalledWith("PATCH", "/api/comments/c1", { body: "16 mm" });
    await deleteComment("c1");
    expect(apiRequestMock).toHaveBeenLastCalledWith("DELETE", "/api/comments/c1");
  });
});

describe("the Tasks area's narrowed requests (lead task 20)", () => {
  it("lists the Inbox with project_id=none", async () => {
    await listTasks({ view: "done", sort: "due", projectId: "none" });
    expect(apiRequestMock).toHaveBeenLastCalledWith("GET", "/api/tasks?project_id=none&view=done&sort=due");
  });

  it("asks a view with its finished (done) tasks: include_finished=1", async () => {
    await listTasks({ view: "upcoming", sort: "due", includeFinished: true, projectId: "p1" });
    expect(apiRequestMock).toHaveBeenLastCalledWith("GET", "/api/tasks?project_id=p1&view=upcoming&sort=due&include_finished=1");
  });

  it("counts everything, one project, or the Inbox", async () => {
    await getTaskCounts();
    expect(apiRequestMock).toHaveBeenLastCalledWith("GET", "/api/tasks/counts");
    await getTaskCounts("p 1");
    expect(apiRequestMock).toHaveBeenLastCalledWith("GET", "/api/tasks/counts?project_id=p+1");
    await getTaskCounts("none");
    expect(apiRequestMock).toHaveBeenLastCalledWith("GET", "/api/tasks/counts?project_id=none");
  });
});
