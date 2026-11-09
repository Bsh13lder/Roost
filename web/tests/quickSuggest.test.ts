import { describe, expect, it } from "vitest";
import { accept, suggest, tokenAt } from "../src/components/tasks/quickSuggest";

const SOURCES = { projects: ["Renovation", "Casa Nueva", "Trip"], tags: ["shopping", "home", "Hobby"], bots: ["Scout", "Money Bot"] };
const caretAtEnd = (text: string) => suggest(text, text.length, SOURCES);

describe("the quick line's suggestions", () => {
  it("offers projects after /, bots after @, levels and star after !", () => {
    expect(caretAtEnd("Paint /")?.options.map((o) => o.insert)).toEqual(["/Renovation", "/Casa Nueva", "/Trip"]);
    expect(caretAtEnd("Paint /re")?.options.map((o) => o.insert)).toEqual(["/Renovation"]);
    expect(caretAtEnd("Call @")?.options.map((o) => o.insert)).toEqual(["@Scout", "@Money Bot"]);
    expect(caretAtEnd("Call @mon")?.options.map((o) => o.insert)).toEqual(["@Money Bot"]);
    expect(caretAtEnd("Pay !")?.options.map((o) => o.insert)).toEqual(["!urgent", "!high", "!medium", "!low", "!star"]);
    expect(caretAtEnd("Pay !h")?.options.map((o) => o.insert)).toEqual(["!high"]);
    expect(caretAtEnd("Pay !alt")?.options.map((o) => o.insert)).toEqual(["!high"]);
    expect(caretAtEnd("Pay !fav")?.options.map((o) => o.insert)).toEqual(["!star"]);
  });

  it("offers existing tags after #, one word only, and never projects", () => {
    expect(caretAtEnd("Milk #")?.options.map((o) => o.insert)).toEqual(["#shopping", "#home", "#Hobby"]);
    expect(caretAtEnd("Milk #ho")?.options.map((o) => o.insert)).toEqual(["#home", "#Hobby"]);
    expect(caretAtEnd("Milk #Ren")).toBeNull(); // Renovation is a project: "/" suggests it
    expect(caretAtEnd("Milk #home alone")).toBeNull();
    expect(caretAtEnd("Milk #home")).toBeNull(); // whole
    const found = caretAtEnd("Milk #sh")!;
    expect(accept("Milk #sh", found, found.options[0]).text).toBe("Milk #shopping ");
  });

  it("offers nothing where no token is being typed", () => {
    expect(caretAtEnd("Paint")).toBeNull();
    expect(caretAtEnd("wow!hi")).toBeNull(); // a ! inside a word is not a token
    expect(caretAtEnd("Mail a@b")).toBeNull();
    expect(caretAtEnd("Paint /zzz")).toBeNull(); // nothing starts like that
    expect(caretAtEnd("Paint /Renovation tomorrow")).toBeNull();
    expect(caretAtEnd("Pay !!!")).toBeNull(); // the shorthand is already whole
    expect(caretAtEnd("Paint /Trip")).toBeNull(); // the whole name typed: nothing left to complete
    expect(caretAtEnd("Pay !high")).toBeNull();
  });

  it("follows the caret, not the end of the text", () => {
    const text = "Paint /re tomorrow";
    const found = suggest(text, "Paint /re".length, SOURCES);
    expect(found?.options.map((o) => o.insert)).toEqual(["/Renovation"]);
    expect(tokenAt(text, "Paint ".length)).toBeNull();
  });

  it("accepting replaces only the token at the caret", () => {
    const text = "Paint /re tomorrow";
    const found = suggest(text, "Paint /re".length, SOURCES)!;
    const picked = accept(text, found, found.options[0]);
    expect(picked.text).toBe("Paint /Renovation tomorrow");
    expect(picked.caret).toBe("Paint /Renovation ".length);
    const atEnd = caretAtEnd("Call @sc")!;
    expect(accept("Call @sc", atEnd, atEnd.options[0])).toEqual({ text: "Call @Scout ", caret: "Call @Scout ".length });
  });

  it("multi-word names are inserted whole and matched across the space", () => {
    const typing = caretAtEnd("Tiles /casa n")!;
    expect(typing.options.map((o) => o.insert)).toEqual(["/Casa Nueva"]);
    expect(accept("Tiles /casa n", typing, typing.options[0]).text).toBe("Tiles /Casa Nueva ");
    const bot = caretAtEnd("Pay @money b")!;
    expect(accept("Pay @money b", bot, bot.options[0]).text).toBe("Pay @Money Bot ");
  });
});
