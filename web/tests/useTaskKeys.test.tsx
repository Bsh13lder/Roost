import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { useTaskKeys } from "../src/components/board/useTaskKeys";
import { makeRow } from "./taskFixtures";

afterEach(() => cleanup());

const ROWS = [makeRow({ id: "a", title: "A" }), makeRow({ id: "b", title: "B" }), makeRow({ id: "c", title: "C" })];

function setup(extra: { enabled?: boolean } = {}) {
  const calls = { onDone: vi.fn(), onTomorrow: vi.fn(), onOpen: vi.fn(), onView: vi.fn(), focusSearch: vi.fn(), focusQuick: vi.fn() };
  function Harness() {
    const [cursor, setCursor] = useState(0);
    useTaskKeys({ enabled: extra.enabled ?? true, rows: ROWS, cursor, setCursor, ...calls });
    return (
      <div>
        <output aria-label="cursor">{cursor}</output>
        <input aria-label="box" />
        <textarea aria-label="notes" />
        <div contentEditable suppressContentEditableWarning aria-label="edit" role="textbox" />
      </div>
    );
  }
  render(<Harness />);
  return calls;
}

const press = (key: string, target: Element | Document = document, init: KeyboardEventInit = {}) =>
  fireEvent.keyDown(target, { key, ...init });
const cursor = () => screen.getByLabelText("cursor").textContent;

describe("useTaskKeys", () => {
  it("j/k/x/t/Enter work and never fire inside an input", () => {
    const calls = setup();
    press("j");
    press("j");
    press("j"); // stops at the last row
    expect(cursor()).toBe("2");
    press("k");
    expect(cursor()).toBe("1");
    press("x");
    expect(calls.onDone).toHaveBeenCalledWith(ROWS[1]);
    press("t");
    expect(calls.onTomorrow).toHaveBeenCalledWith(ROWS[1]);
    press("Enter");
    expect(calls.onOpen).toHaveBeenCalledWith("b");
    for (const label of ["box", "notes", "edit"]) {
      const field = screen.getByLabelText(label);
      press("j", field);
      press("x", field);
      press("Enter", field);
    }
    expect(cursor()).toBe("1");
    expect(calls.onDone).toHaveBeenCalledTimes(1);
    expect(calls.onOpen).toHaveBeenCalledTimes(1);
  });

  it("1–5 switch views, / focuses search and q the quick line", () => {
    const calls = setup();
    for (const [key, view] of [["1", "today"], ["2", "upcoming"], ["3", "overdue"], ["4", "someday"], ["5", "done"]]) {
      press(key);
      expect(calls.onView).toHaveBeenLastCalledWith(view);
    }
    press("/");
    press("q");
    expect(calls.focusSearch).toHaveBeenCalledTimes(1);
    expect(calls.focusQuick).toHaveBeenCalledTimes(1);
  });

  it("does nothing when it is off, with a modifier held, or while a dialog or menu is open", () => {
    const off = setup({ enabled: false });
    press("x");
    expect(off.onDone).not.toHaveBeenCalled();
    cleanup();
    const on = setup();
    press("x", document, { metaKey: true });
    expect(on.onDone).not.toHaveBeenCalled();
    const dialog = document.createElement("div");
    dialog.setAttribute("role", "dialog");
    document.body.append(dialog);
    press("x");
    expect(on.onDone).not.toHaveBeenCalled();
    dialog.remove();
    press("x");
    expect(on.onDone).toHaveBeenCalledTimes(1);
  });

  it("removes its listener when it unmounts", () => {
    const calls = setup();
    cleanup();
    press("x");
    expect(calls.onDone).not.toHaveBeenCalled();
  });
});
