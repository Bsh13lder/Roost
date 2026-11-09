import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { ProgramActivityRow } from "../src/components/chat/ProgramActivityRow";
import { parseProgramActivity, programActivityLine } from "../src/lib/programActivity";
import { makeMessage } from "./fixtures";

afterEach(cleanup);

const line = (over: Record<string, unknown> = {}) => makeMessage({
  id: "run-1", role: "activity", kind: "program_activity", author_bot_id: "bot-1",
  body: JSON.stringify({ op: "run", command: "python3 sum.py", exit_code: 0, timed_out: false, output: "6\n<b>x</b>",
    cut: false, tainted_basis: false, ...over }),
});
const row = (message = line()) => render(<ul><ProgramActivityRow message={message} /></ul>);

describe("ProgramActivityRow", () => {
  it("shows the command and exit code, with the output folded as plain text", () => {
    const { container } = row();
    expect(screen.getByText("Ran: python3 sum.py · exit 0")).toBeInTheDocument();
    const details = container.querySelector("details");
    expect(details).not.toBeNull();
    expect(details?.open).toBe(false);
    expect(container.querySelector("pre")?.textContent).toBe("6\n<b>x</b>");
    expect(container.querySelector("b")).toBeNull();
  });

  it("marks a failure or a timeout and says when the output was cut", () => {
    row(line({ exit_code: -1, timed_out: true, cut: true }));
    expect(screen.getByText("Ran: python3 sum.py · timed out")).toHaveClass("program-activity--failed");
    expect(screen.getByText("Output (cut)")).toBeInTheDocument();
  });

  it("a file write is one line with no output", () => {
    const { container } = row(line({ op: "write", path: "src/a.py", command: undefined, output: "" }));
    expect(screen.getByText("Wrote src/a.py")).toBeInTheDocument();
    expect(container.querySelector("details")).toBeNull();
  });

  it("a body it can't read falls back to words", () => {
    row(makeMessage({ id: "x", role: "activity", kind: "program_activity", body: "nope" }));
    expect(screen.getByText("Ran a program")).toBeInTheDocument();
  });
});

describe("programActivityLine", () => {
  it("keeps a command on one line", () => {
    expect(programActivityLine(parseProgramActivity(JSON.stringify({ op: "run", command: "echo a\necho b", exit_code: 2 }))))
      .toBe("Ran: echo a echo b · exit 2");
    expect(parseProgramActivity(JSON.stringify({ op: "delete", path: "a" }))).toBeNull();
    expect(parseProgramActivity(JSON.stringify({ op: "run" }))).toBeNull();
  });
});
