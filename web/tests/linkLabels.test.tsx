import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import Markdown from "../src/components/markdown/Markdown";
import { PlainText } from "../src/components/chat/PlainText";

afterEach(cleanup);

describe("links show their real host", () => {
  it("a bare URL in plain text shows its host", () => {
    render(<PlainText text="The invoice is at https://dashboard.stripe.com/invoices/in_123?x=1 today." keyPrefix="m" />);
    const link = screen.getByRole("link", { name: "dashboard.stripe.com" });
    expect(link).toHaveAttribute("href", "https://dashboard.stripe.com/invoices/in_123?x=1");
    expect(screen.queryByText(/in_123/)).toBeNull();
  });

  it("a bare URL in markdown shows its host", () => {
    render(<Markdown text="See https://docs.example/guide/long/path for it." />);
    expect(screen.getByRole("link", { name: "docs.example" })).toHaveAttribute("href", "https://docs.example/guide/long/path");
  });

  it("a labelled markdown link shows the real host, not the label", () => {
    render(<Markdown text="Pay at [your bank](https://evil.example/login)." />);
    expect(screen.getByRole("link", { name: "evil.example" })).toBeInTheDocument();
    expect(screen.queryByText("your bank")).toBeNull();
  });
});
