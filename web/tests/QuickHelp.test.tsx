import { readFileSync } from "node:fs";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QuickHelp } from "../src/components/tasks/QuickHelp";
import { EXPENSE_TOKENS, TASK_TOKENS } from "../src/components/tasks/quickHelpTokens";

afterEach(() => cleanup());

describe("the quick line's help", () => {
  it("lists every token with an English and a Spanish example", async () => {
    render(<QuickHelp />);
    await userEvent.click(screen.getByRole("button", { name: "Quick line help" }));
    const panel = await screen.findByRole("dialog", { name: "Quick line help" });
    expect(TASK_TOKENS.length).toBeGreaterThanOrEqual(9);
    for (const row of TASK_TOKENS) {
      expect(row.en.length).toBeGreaterThan(0);
      expect(row.es.length).toBeGreaterThan(0);
      for (const text of [row.token, row.en, row.es, row.means]) expect(within(panel).getByText(text)).toBeInTheDocument();
    }
  });

  it("can show the expense line's tokens instead", async () => {
    render(<QuickHelp tokens={EXPENSE_TOKENS} />);
    await userEvent.click(screen.getByRole("button", { name: "Quick line help" }));
    const panel = await screen.findByRole("dialog", { name: "Quick line help" });
    for (const row of EXPENSE_TOKENS) expect(within(panel).getByText(row.es)).toBeInTheDocument();
    expect(within(panel).queryByText("@Scout")).not.toBeInTheDocument();
  });

  it("is one column at phone width", async () => {
    render(<QuickHelp />);
    await userEvent.click(screen.getByRole("button", { name: "Quick line help" }));
    const panel = await screen.findByRole("dialog", { name: "Quick line help" });
    expect(panel.querySelector(".quick-help__list")).toBeInTheDocument();
    expect(panel.querySelectorAll(".quick-help__row").length).toBe(TASK_TOKENS.length);
    // The stylesheet puts a row's parts in one column inside the phone breakpoint.
    const css = readFileSync(join(process.cwd(), "src/styles/tasks.css"), "utf8");
    const phone = css.slice(css.indexOf("@media (max-width: 768px)", css.indexOf(".quick-help")));
    expect(phone).toMatch(/\.quick-help__row\s*\{[^}]*grid-template-columns:\s*1fr/);
  });
});
