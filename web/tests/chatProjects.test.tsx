import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Composer } from "../src/components/Composer";
import { WebMark } from "../src/components/chat/WebMark";
import { insertMention, mentionQuery } from "../src/lib/mentions";
import { splitProjectTokens } from "../src/lib/projectTokens";

afterEach(cleanup);

const PROJECTS = [{ id: "p1", name: "Casa" }, { id: "p2", name: "Casa Nueva" }, { id: "p3", name: "Garden" }];
const TEAM = [{ id: "s", name: "Scout" }];

describe("the # word at the caret", () => {
  it("opens only at the start or after a space, and picking writes #Name", () => {
    expect(mentionQuery("tasks for #Ca", "#")).toBe("Ca");
    expect(mentionQuery("#", "#")).toBe("");
    expect(mentionQuery("issue a#1", "#")).toBeNull();
    expect(mentionQuery("tasks for #Ca", "@")).toBeNull();
    expect(insertMention("show #ca", 8, "Casa Nueva", "#")).toEqual({ text: "show #Casa Nueva ", caret: 17 });
  });
});

describe("splitProjectTokens", () => {
  it("reads known names exactly, longest first, any case, never inside a word", () => {
    expect(splitProjectTokens("left in #casa nueva?", PROJECTS)).toEqual([
      { text: "left in " }, { text: "#casa nueva", project: PROJECTS[1] }, { text: "?" },
    ]);
    expect(splitProjectTokens("#Casa and #Gardens and x#Garden", PROJECTS)).toEqual([
      { text: "#Casa", project: PROJECTS[0] }, { text: " and #Gardens and x#Garden" },
    ]);
    expect(splitProjectTokens("no tokens", PROJECTS)).toEqual([{ text: "no tokens" }]);
    expect(splitProjectTokens("#Casa", [])).toEqual([{ text: "#Casa" }]);
  });
});

describe("Composer # list", () => {
  it("typing # lists your projects, filters as you type, and Enter picks one without sending", async () => {
    const onSend = vi.fn();
    render(<Composer onSend={onSend} mentions={TEAM} projects={PROJECTS} />);
    const box = screen.getByRole("textbox");
    await userEvent.type(box, "tasks in #");
    expect(screen.getByRole("listbox", { name: "Project" })).toBeInTheDocument();
    expect(screen.getAllByRole("option").map((o) => o.textContent)).toEqual(["#Casa", "#Casa Nueva", "#Garden"]);
    await userEvent.type(box, "ca");
    expect(screen.getAllByRole("option").map((o) => o.textContent)).toEqual(["#Casa", "#Casa Nueva"]);
    await userEvent.keyboard("{ArrowDown}{Enter}");
    expect(box).toHaveValue("tasks in #Casa Nueva ");
    expect(onSend).not.toHaveBeenCalled();
    await userEvent.type(box, "@");
    expect(screen.getAllByRole("option").map((o) => o.textContent)).toEqual(["@Scout"]);
  });

  it("with no projects, # opens nothing", async () => {
    render(<Composer onSend={vi.fn()} mentions={TEAM} />);
    await userEvent.type(screen.getByRole("textbox"), "#");
    expect(screen.queryByRole("listbox")).toBeNull();
  });
});

describe("WebMark", () => {
  it("is a quiet Web chip that explains itself when tapped", async () => {
    render(<WebMark />);
    const mark = screen.getByRole("button", { name: "From web content" });
    expect(mark).toHaveTextContent("Web");
    await userEvent.click(mark);
    expect(await screen.findByText(/Part of this came from a web page/)).toBeInTheDocument();
  });
});
