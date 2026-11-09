import { afterEach, describe, expect, it } from "vitest";
import { ALL_TASKS, TASK_SCOPE_STORAGE_KEY, inScope, parseScope, readScope, rememberScope, scopeParam, scopeProjectId, scopeQuery } from "../src/components/board/taskScope";

afterEach(() => window.localStorage.clear());

describe("a Tasks selection", () => {
  it("reads the address: none or all is All, anything else a project", () => {
    expect(parseScope(null)).toEqual(ALL_TASKS);
    expect(parseScope("")).toEqual(ALL_TASKS);
    expect(parseScope("all")).toEqual(ALL_TASKS);
    expect(parseScope("p1")).toEqual({ kind: "project", id: "p1" });
  });

  it("inbox is the tasks with no project", () => {
    expect(parseScope("inbox")).toEqual({ kind: "inbox" });
    expect(scopeParam({ kind: "inbox" })).toBe("inbox");
    expect(inScope({ project_id: null }, { kind: "inbox" })).toBe(true);
    expect(inScope({ project_id: "p1" }, { kind: "inbox" })).toBe(false);
    expect(inScope({ project_id: "p1" }, ALL_TASKS)).toBe(true);
  });

  it("asks the server with project_id: the id, \"none\" for the Inbox, nothing for All", () => {
    expect(scopeQuery({ kind: "project", id: "p1" })).toBe("p1");
    expect(scopeQuery({ kind: "inbox" })).toBe("none");
    expect(scopeQuery({ kind: "all" })).toBeUndefined();
    expect(scopeProjectId({ kind: "inbox" })).toBeUndefined(); // a new task in the Inbox has no project
  });

  it("writes the address back: All has no param", () => {
    expect(scopeParam(ALL_TASKS)).toBeNull();
    expect(scopeParam({ kind: "project", id: "p1" })).toBe("p1");
  });

  it("is remembered in this browser under one key; All forgets", () => {
    rememberScope({ kind: "project", id: "p1" });
    expect(window.localStorage.getItem(TASK_SCOPE_STORAGE_KEY)).toBe("p1");
    expect(readScope()).toBe("p1");
    rememberScope(ALL_TASKS);
    expect(readScope()).toBeNull();
  });
});
