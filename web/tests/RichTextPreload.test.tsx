import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render } from "@testing-library/react";
import { preloadMarkdown, RichText } from "../src/components/chat/RichText";

afterEach(() => cleanup());

// Final-review fix: a chat preloads the markdown renderer when it opens (pages/Chat.tsx, pages/Room.tsx), so
// its first replies are drawn as markdown at once instead of flashing from plain text to markdown.
describe("preloading the markdown renderer", () => {
  it("draws a reply's markdown on its very first frame once the renderer is preloaded", async () => {
    await preloadMarkdown();
    const { container } = render(<RichText text="**Done.** See [[Garden plan]]." id="m-1" />);
    expect(container.querySelector("strong")).toHaveTextContent("Done.");
    expect(container.querySelector(".wikilink-chip")).toHaveTextContent("Garden plan");
    expect(container.querySelector(".message__plain")).toBeNull();
  });

  it("can be asked again and again, and still resolves", async () => {
    await expect(Promise.all([preloadMarkdown(), preloadMarkdown()])).resolves.toEqual([undefined, undefined]);
  });
});
