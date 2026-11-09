import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DiffView } from "../src/components/approvals/DiffView";
import { makeApprovalCard, makeStep } from "./fixtures";

const getMock = vi.fn();
vi.mock("../src/api/approvals", () => ({ getApproval: (id: string, full: boolean) => getMock(id, full) }));
afterEach(() => { cleanup(); getMock.mockReset(); });

describe("DiffView", () => {
  it("colours added and removed lines and counts them", () => {
    const diff = { text: "@@ -1,2 +1,2 @@\n keep\n-old\n+new", plus: 1, minus: 1, truncated: false };
    render(<DiffView cardId="c" stepIndex={0} diff={diff} />);
    expect(screen.getByText("+1 −1 lines")).toBeInTheDocument();
    expect(screen.getByText("+new")).toHaveClass("diff__line--add");
    expect(screen.getByText("-old")).toHaveClass("diff__line--remove");
    expect(screen.getByText("keep")).not.toHaveClass("diff__line--add");
    expect(screen.queryByRole("button", { name: "Open full diff" })).not.toBeInTheDocument();
  });

  it("shows text as text, never as markup", () => {
    const diff = { text: "+<img src=x onerror=alert(1)>", plus: 1, minus: 0, truncated: false };
    const { container } = render(<DiffView cardId="c" stepIndex={0} diff={diff} />);
    expect(container.querySelector("img")).toBeNull();
    expect(screen.getByText("+<img src=x onerror=alert(1)>")).toBeInTheDocument();
  });

  it("a long diff shows 400 lines and opens the full one", async () => {
    const lines = (n: number) => Array.from({ length: n }, (_, i) => `+line ${i}`).join("\n");
    getMock.mockResolvedValue(makeApprovalCard({ steps: [makeStep({ diff: { text: lines(500), plus: 500, minus: 0, truncated: false } })] }));
    render(<DiffView cardId="card-a" stepIndex={0} diff={{ text: lines(400), plus: 500, minus: 0, truncated: true }} />);
    expect(screen.getAllByText(/^\+line \d+$/)).toHaveLength(400);
    await userEvent.click(screen.getByRole("button", { name: "Open full diff" }));
    expect(getMock).toHaveBeenCalledWith("card-a", true);
    expect(await screen.findByText("+line 499")).toBeInTheDocument();
    expect(screen.getAllByText(/^\+line \d+$/)).toHaveLength(500);
    expect(screen.queryByRole("button", { name: "Open full diff" })).not.toBeInTheDocument();
  });

  it("a diff with no text yet (a live card) opens the full one too", async () => {
    getMock.mockResolvedValue(makeApprovalCard({ steps: [makeStep({ diff: { text: "+a", plus: 1, minus: 0, truncated: false } })] }));
    render(<DiffView cardId="card-a" stepIndex={0} diff={{ text: "", plus: 1, minus: 0, truncated: true }} />);
    await userEvent.click(screen.getByRole("button", { name: "Open full diff" }));
    expect(await screen.findByText("+a")).toBeInTheDocument();
  });

  it("says why the full diff did not open", async () => {
    getMock.mockRejectedValue(new Error("boom"));
    render(<DiffView cardId="c" stepIndex={0} diff={{ text: "+a", plus: 1, minus: 0, truncated: true }} />);
    await userEvent.click(screen.getByRole("button", { name: "Open full diff" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});
