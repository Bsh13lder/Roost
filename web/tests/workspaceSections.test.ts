import { describe, expect, it } from "vitest";
import { sectionOf } from "../src/components/workspace/sections";

const read = (search: string) => sectionOf(new URLSearchParams(search));

describe("the Workspace's sections", () => {
  it("opens on Tasks when the address names none, or an unknown one", () => {
    expect(read("")).toBe("tasks");
    expect(read("tab=tasks")).toBe("tasks");
    expect(read("tab=nonsense")).toBe("tasks");
  });

  it("keeps the old Board links working: notes and documents are Notes, money is All money", () => {
    expect(read("tab=notes&note=n1")).toBe("notes");
    expect(read("tab=documents&document=d1")).toBe("notes");
    expect(read("tab=money")).toBe("money");
    expect(read("tab=calendar")).toBe("calendar");
  });

  it("sends the old Tasks calendar layout to the Calendar section", () => {
    expect(read("tab=tasks&layout=calendar")).toBe("calendar");
    expect(read("tab=tasks&layout=kanban")).toBe("tasks");
  });
});
