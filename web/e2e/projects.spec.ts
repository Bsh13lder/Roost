import { expect, test, type Locator, type Page } from "@playwright/test";
import { formatMoney } from "../src/components/board/money";
import { detailPane, openBoard, signIn } from "./helpers";

// Projects hub (design P2–P4, P6, P7 and §5 H4, H6, H8, H9, H14), through the Board only. No bot is
// involved, so fixtures/team-script.json is untouched. Amounts are what the web shows, formatted by
// its own formatMoney (en-IE): "€2,500.00". The server does every sum (H8); this spec only reads them,
// so the amounts left are written down here, never computed.
const PROJECT = "Renovation";
const NOTE = "Kitchen tiles";
const CURRENCY = "EUR";               // the New project form's default
const TOTAL = "3000";
const MONTHLY = "1000";
const SPENT = "2500";
const TOP_UP = "500";
const TOTAL_WITH_TOP_UP = "3500";
const LEFT = "500";                   // 3000 − 2500
const LEFT_WITH_TOP_UP = "1000";      // 3500 − 2500
const MONTH_OVER = "1500";            // 2500 spent this month against the 1000 monthly limit
const eur = (amount: string): string => formatMoney(amount, CURRENCY);

// A stat of the header card (G13): its value, its small words, its meter's aria-valuenow (the server's
// used_percent, rounded down and clamped to 0–100) and the server's tone, which names the fill's class.
type Tone = "ok" | "warn" | "over";
type Bar = readonly [value: string, small: string, percent: string, tone: Tone];
const FRESH_TOTAL: Bar = [eur(TOTAL), `left of ${eur(TOTAL)}`, "0", "ok"];
const FRESH_MONTH: Bar = [eur(MONTHLY), `left of ${eur(MONTHLY)}`, "0", "ok"];
const SPENT_TOTAL: Bar = [eur(LEFT), `left of ${eur(TOTAL)}`, "83", "warn"];                 // amber from 80 %
const TOPPED_UP_TOTAL: Bar = [eur(LEFT_WITH_TOP_UP), `left of ${eur(TOTAL_WITH_TOP_UP)}`, "71", "ok"];
const OVER_MONTH: Bar = [eur(MONTH_OVER), `over ${eur(MONTHLY)}`, "100", "over"];            // the server says 250

const history = (detail: Locator): Locator => detail.getByRole("list", { name: "Top-up history" });
const STATS = { "Total budget": 0, "This month": 1 } as const;
const expenseRow = (detail: Locator): Locator =>
  detail.getByRole("list", { name: "Expenses" }).getByRole("listitem").filter({ hasText: NOTE });

async function expectBar(detail: Locator, name: keyof typeof STATS, [value, small, percent, tone]: Bar): Promise<void> {
  const stat = detail.locator(".p-stat").nth(STATS[name]);
  await expect(stat).toContainText(value);
  await expect(stat).toContainText(small);
  await expect(stat.getByRole("meter")).toHaveAttribute("aria-valuenow", percent);
  await expect(stat.locator(`.meter__fill--${tone}`)).toHaveCount(1);
}

async function expectBars(detail: Locator, total: Bar, month: Bar): Promise<void> {
  await expectBar(detail, "Total budget", total);
  await expectBar(detail, "This month", month);
}

// New project is in the Workspace's project chips menu; its form opens in a sheet, and the new project's chip is picked.
async function createProject(detail: Locator): Promise<void> {
  await detail.getByRole("button", { name: "Projects and money" }).click();
  await detail.page().getByRole("menuitem", { name: "New project" }).click();
  const form = detail.page().getByRole("form", { name: "New project", exact: true });
  await form.getByLabel("Name", { exact: true }).fill(PROJECT);
  await expect(form.getByLabel("Currency", { exact: true })).toHaveValue(CURRENCY);
  await form.getByLabel("Total budget", { exact: true }).fill(TOTAL);
  await form.getByLabel("Monthly limit", { exact: true }).fill(MONTHLY);
  await form.getByRole("button", { name: "Create project", exact: true }).click();
  await expect(form).toHaveCount(0);
  await expect(detail.getByRole("group", { name: "Filter by project" }).getByRole("button", { name: PROJECT, exact: true }))
    .toHaveAttribute("aria-pressed", "true");
}

async function openProjectMoney(page: Page, detail: Locator): Promise<void> {
  await detail.getByRole("link", { name: "Open project ›", exact: true }).click();   // the picked project's card
  await page.waitForURL(/\/board\/projects\/[^/?]+/);
  await expect(detail.getByRole("heading", { name: PROJECT, exact: true })).toBeVisible();
  // The project's page holds its tasks, then its money: no Money tab to open.
  await expectBars(detail, FRESH_TOTAL, FRESH_MONTH);
  // H4: the budget given at creation is the history's first row ("+€3,000.00"). The card folds its list.
  await detail.getByRole("button", { name: /^Top-ups/ }).click();
  await expect(history(detail).getByRole("listitem").filter({ hasText: "Budget set" })).toContainText(eur(TOTAL));
}

async function addExpense(detail: Locator): Promise<Locator> {
  // The expense line (Task 7): a project's page files the line under that project.
  await detail.getByRole("combobox", { name: "New expense", exact: true }).fill(`€${SPENT} ${NOTE}`);
  await detail.getByRole("combobox", { name: "New expense", exact: true }).press("Enter");
  const expense = expenseRow(detail);
  await expect(expense).toContainText(eur(SPENT));
  await expectBars(detail, SPENT_TOTAL, OVER_MONTH);                         // the month is over its limit
  return expense;
}

async function topUpThenUndo(detail: Locator): Promise<void> {
  await detail.getByRole("button", { name: "Add top-up", exact: true }).click();
  await detail.getByRole("textbox", { name: "Top-up amount", exact: true }).fill(TOP_UP);
  await detail.getByRole("button", { name: "Add top-up", exact: true }).click();
  await expectBars(detail, TOPPED_UP_TOTAL, OVER_MONTH);                     // the top-up raises the total budget
  const topUp = history(detail).getByRole("listitem").filter({ hasText: "Top-up" }).filter({ hasText: eur(TOP_UP) });
  const undo = topUp.getByRole("button", { name: `Undo the top-up of ${eur(TOP_UP)}`, exact: true });
  await undo.click();
  await expectBars(detail, SPENT_TOTAL, OVER_MONTH);                         // and its undo takes it back off
  await expect(topUp).toContainText("undone");                               // still in the history, marked
  await expect(undo).toHaveCount(0);
}

async function starThenVoid(detail: Locator, expense: Locator): Promise<void> {
  const star = expense.getByRole("button", { name: `Star the ${PROJECT} expense`, exact: true });
  await star.click();
  await expect(star).toHaveAttribute("aria-pressed", "true");
  await expense.getByRole("button", { name: `More for the ${PROJECT} expense`, exact: true }).click();
  await detail.page().getByRole("menuitem", { name: "Void", exact: true }).click();    // G9: Void is in the ⋯ menu
  await expect(expense).toHaveClass(/is-void/);                                      // H6: still listed, marked
  await expectBars(detail, FRESH_TOTAL, FRESH_MONTH);                              // and counted in neither bar
}

async function deleteProject(page: Page, detail: Locator): Promise<void> {
  await detail.getByRole("button", { name: `More for ${PROJECT}`, exact: true }).click();
  await page.getByRole("menuitem", { name: "Delete", exact: true }).click();
  await expect(detail.getByRole("group", { name: `Delete ${PROJECT}?`, exact: true }))
    .toContainText("Its expenses move to General");
  await detail.getByRole("button", { name: `Delete ${PROJECT} for good`, exact: true }).click();
  // Back to the Workspace's Tasks on All (?project=all drops out of the address), and no chip names it.
  await page.waitForURL(/\/board\?tab=tasks$/);
  const chips = detail.getByRole("group", { name: "Filter by project" });
  await expect(chips.getByRole("button", { name: "All", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect(chips.getByRole("button", { name: PROJECT, exact: true })).toHaveCount(0);
}

test("a project with a total budget and a monthly limit: an expense, a top-up and its undo, star and void, then delete it", async ({ page }) => {
  test.setTimeout(60_000);
  await signIn(page);
  await openBoard(page);
  const detail = detailPane(page);
  // The Workspace opens on Tasks, whose chips hold the projects.
  await expect(detail.getByRole("group", { name: "Workspace sections" }).getByRole("button", { name: "Tasks" }))
    .toHaveAttribute("aria-pressed", "true");
  await createProject(detail);
  await openProjectMoney(page, detail);
  const expense = await addExpense(detail);
  await topUpThenUndo(detail);
  await starThenVoid(detail, expense);
  await deleteProject(page, detail);

  // H9: the project is gone but its expense is not. It moved to General, void as it was, and All money lists it there.
  await detail.getByRole("button", { name: "Projects and money" }).click();
  await page.getByRole("menuitem", { name: "All money" }).click();
  const moved = expenseRow(detail);
  await expect(moved.locator(".xp__tag")).toHaveText("General");
  await expect(moved).toContainText(eur(SPENT));
  await expect(moved).toHaveClass(/is-void/);
});
