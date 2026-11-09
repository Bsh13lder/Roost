import { describe, expect, it } from "vitest";
import { linkHost } from "../src/lib/linkHost";

// M1's link rule: a link shows its real host and goes to the address that host names. The href is the
// parsed absolute URL, never the raw string, which a browser would resolve against this page.
describe("linkHost", () => {
  it("gives the host and the parsed absolute address of an http(s) URL", () => {
    expect(linkHost("https://docs.example/guide")).toEqual({ host: "docs.example", href: "https://docs.example/guide" });
    expect(linkHost("HTTPS://Docs.Example")).toEqual({ host: "docs.example", href: "https://docs.example/" });
  });

  it("parses a slashless http(s) URL to the address its host names (review fix)", () => {
    expect(linkHost("http:bank.example/login")).toEqual({ host: "bank.example", href: "http://bank.example/login" });
    expect(linkHost("http:/bank.example/login")).toEqual({ host: "bank.example", href: "http://bank.example/login" });
    expect(linkHost("https:evil.example")).toEqual({ host: "evil.example", href: "https://evil.example/" });
  });

  it("refuses anything that is not an absolute http(s) URL", () => {
    for (const href of [undefined, "", "/bots/x", "bank.example/login", "//evil.example/x", "javascript:alert(1)",
      "mailto:a@b.example", "data:text/html,x", "http:", "https://"]) {
      expect(linkHost(href)).toBeNull();
    }
  });
});
