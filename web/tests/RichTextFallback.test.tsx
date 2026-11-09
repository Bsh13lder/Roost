import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { preloadMarkdown, RichText } from "../src/components/chat/RichText";

// Review Focus 2: the markdown chunk fails to load (a deploy renamed it while this tab stayed open).
vi.mock("../src/components/markdown/Markdown", () => {
  throw new Error("Failed to fetch dynamically imported module");
});

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe("RichText when the markdown renderer cannot load", () => {
  it("keeps the plain text, links drawn as their real host, instead of blanking the chat", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    render(<RichText text="**Done.** See https://example.com/x" id="m-1" />);
    await vi.waitFor(() => expect(warn).toHaveBeenCalled());
    expect(screen.getByText("**Done.** See", { exact: false })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "example.com" })).toHaveAttribute("href", "https://example.com/x");
  });

  // Final-review fix: the chat's preload fails the same way. It is logged, never thrown at the page, and the
  // replies still show their plain text.
  it("logs a preload that fails, and the replies keep their plain text", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    await expect(preloadMarkdown()).resolves.toBeUndefined();
    expect(warn).toHaveBeenCalledWith(expect.stringContaining("plain text"), expect.any(Error));
    render(<RichText text="**Done.**" id="m-2" />);
    expect(screen.getByText("**Done.**")).toBeInTheDocument();
  });
});
