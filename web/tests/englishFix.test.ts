import { describe, expect, it } from "vitest";
import {
  englishFixFor, fixSegments, isEnglishFix, parseEnglishFix, placeEnglishFixes,
} from "../src/lib/englishFix";
import { makeMessage } from "./fixtures";

const FIX = {
  message_id: "u1",
  said: "I goed to the shop yesterday and buyed milk",
  corrected: "I went to the shop yesterday and bought milk",
  fixes: [{ wrong: "goed", right: "went" }, { wrong: "buyed", right: "bought" }],
};
const fixMessage = (id: string, body: unknown, seq: number) =>
  makeMessage({ id, role: "activity", kind: "english_fix", body: JSON.stringify(body), seq });

describe("parseEnglishFix", () => {
  it("reads the server's body", () => {
    expect(parseEnglishFix(JSON.stringify(FIX))).toEqual(FIX);
  });

  it("refuses anything that is not a whole english_fix body", () => {
    expect(parseEnglishFix("not json")).toBeNull();
    expect(parseEnglishFix(JSON.stringify({ ...FIX, said: 3 }))).toBeNull();
    expect(parseEnglishFix(JSON.stringify({ ...FIX, fixes: [{ wrong: "a" }] }))).toBeNull();
    expect(parseEnglishFix(JSON.stringify({ ...FIX, message_id: "" }))).toBeNull();
    expect(parseEnglishFix(JSON.stringify({ ...FIX, corrected: "" }))).toBeNull();
    expect(parseEnglishFix(JSON.stringify([FIX]))).toBeNull();
  });
});

describe("fixSegments", () => {
  it("shows each fix inline: the wrong words struck through, the right words beside them", () => {
    expect(fixSegments(FIX)).toEqual({
      segments: [
        { kind: "text", text: "I " },
        { kind: "wrong", text: "goed" },
        { kind: "right", text: "went" },
        { kind: "text", text: " to the shop yesterday and " },
        { kind: "wrong", text: "buyed" },
        { kind: "right", text: "bought" },
        { kind: "text", text: " milk" },
      ],
      trailing: [],
    });
  });

  it("a fix whose wrong words are not in what you said goes at the end as wrong → right", () => {
    const shown = fixSegments({ ...FIX, fixes: [{ wrong: "goed", right: "went" }, { wrong: "purchased", right: "bought" }] });
    expect(shown.segments).toEqual([
      { kind: "text", text: "I " },
      { kind: "wrong", text: "goed" },
      { kind: "right", text: "went" },
      { kind: "text", text: " to the shop yesterday and bought milk" },
    ]);
    expect(shown.trailing).toEqual([{ wrong: "purchased", right: "bought" }]);
  });

  it("a fix whose right words are not in the corrected sentence goes at the end too", () => {
    const shown = fixSegments({ said: "me want it", corrected: "I want it", fixes: [{ wrong: "me", right: "I would" }] });
    expect(shown.segments).toEqual([{ kind: "text", text: "I want it" }]);
    expect(shown.trailing).toEqual([{ wrong: "me", right: "I would" }]);
  });

  it("an added word has nothing to strike through", () => {
    const shown = fixSegments({ said: "I want apple", corrected: "I want an apple", fixes: [{ wrong: "", right: "an " }] });
    expect(shown.segments).toEqual([
      { kind: "text", text: "I want " }, { kind: "right", text: "an " }, { kind: "text", text: "apple" },
    ]);
  });

  it("with no fixes the corrected sentence is one plain piece", () => {
    expect(fixSegments({ said: "Fine.", corrected: "Fine.", fixes: [] })).toEqual({
      segments: [{ kind: "text", text: "Fine." }], trailing: [],
    });
  });
});

describe("placing english_fix lines", () => {
  const mine = makeMessage({ id: "u1", role: "user", body: FIX.said, seq: 1 });
  const reply = makeMessage({ id: "b1", role: "bot", body: "Sure.", seq: 2 });

  it("knows an english_fix line", () => {
    expect(isEnglishFix(fixMessage("f1", FIX, 3))).toBe(true);
    expect(isEnglishFix(mine)).toBe(false);
    expect(isEnglishFix(makeMessage({ role: "activity", kind: "memory_note" }))).toBe(false);
  });

  it("lifts a line under the message it names, out of the flow", () => {
    const fix = fixMessage("f1", FIX, 3);
    const placed = placeEnglishFixes([mine, reply, fix]);
    expect(placed.rows.map((m) => m.id)).toEqual(["u1", "b1"]);
    expect([...placed.under.keys()]).toEqual(["u1"]);
    expect(placed.under.get("u1")).toEqual([fix]);
  });

  it("leaves a line in its own place when the message it names is not loaded", () => {
    const orphan = fixMessage("f2", { ...FIX, message_id: "gone" }, 3);
    const placed = placeEnglishFixes([mine, reply, orphan]);
    expect(placed.rows.map((m) => m.id)).toEqual(["u1", "b1", "f2"]);
    expect(placed.under.size).toBe(0);
  });

  it("an unreadable line stays where it is", () => {
    const broken = makeMessage({ id: "f3", role: "activity", kind: "english_fix", body: "???", seq: 3 });
    const placed = placeEnglishFixes([mine, broken]);
    expect(placed.rows.map((m) => m.id)).toEqual(["u1", "f3"]);
  });

  it("englishFixFor gives the newest line for your message", () => {
    const older = fixMessage("f1", { ...FIX, corrected: "older" }, 3);
    const newer = fixMessage("f2", { ...FIX, corrected: "I went to the shop" }, 4);
    const other = fixMessage("f3", { ...FIX, message_id: "u9" }, 5);
    expect(englishFixFor([mine, older, newer, other], "u1")?.corrected).toBe("I went to the shop");
    expect(englishFixFor([mine, other], "u1")).toBeNull();
  });
});
