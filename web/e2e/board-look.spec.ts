import { expect, test, type Locator, type Page } from "@playwright/test";
import { addDays, dayText, todayIn } from "../src/ui/date/dates";
import { detailPane, openTaskView, signIn } from "./helpers";

// The Board redesign end to end (Tasks & Money plan, Task 16; the Workspace since the app restructure), on the
// scripted gateway. Every date is Madrid's
// today or a helper offset from it, never a clock time, and every name is this spec's own: the Board is shared
// with the other specs, so counts are read from the server and compared, never assumed.
const ORIGIN = "http://127.0.0.1";

interface Made { id: string }
interface Counts { overdue: number; today: number; upcoming_14: number }

async function post(page: Page, path: string, data: object): Promise<Made> {
  const origin = `${ORIGIN}:${new URL(page.url()).port || "80"}`;
  const response = await page.request.post(path, { data, headers: { Origin: origin } });
  expect(response.ok(), `${path}: ${await response.text()}`).toBe(true);
  return response.json() as Promise<Made>;
}

async function counts(page: Page): Promise<Counts> {
  return (await page.request.get("/api/tasks/counts")).json() as Promise<Counts>;
}

const toast = (page: Page): Locator => page.locator(".toast-region");

// A day of this month that is not in the future, so an expense can be dated on it.
function pastDayThisMonth(today: string): string {
  return today.endsWith("-01") ? today : addDays(today, -1);
}

test("the pill adds with chips, says Added with Open, and Upcoming holds the task with its project pill", async ({ page }) => {
  test.setTimeout(60_000);
  await signIn(page);
  await post(page, "/api/projects", { name: "Greenhouse" });
  const tomorrow = addDays(todayIn(), 1);
  await page.goto("/board?tab=tasks");
  const detail = detailPane(page);
  const pill = detail.getByRole("combobox", { name: "Add or find anything" });
  await pill.fill("Water the ferns tomorrow 9am /Greenhouse #outdoor !high");
  for (const chip of [`${dayText(tomorrow, { weekday: true })} 09:00`, "/Greenhouse", "#outdoor", "!high"]) {
    await expect(detail.locator(".quick-chip--read", { hasText: chip })).toBeVisible();
  }
  await pill.press("Enter");
  await expect(toast(page)).toContainText("Added “Water the ferns”");
  await expect(pill).toHaveValue("");
  await openTaskView(page, "Upcoming");
  const row = detail.getByRole("row").filter({ hasText: "Water the ferns" });
  await expect(row.getByRole("link", { name: "Greenhouse" })).toHaveAttribute("href", /\/board\/projects\//);
});

test("the counts follow the server, and Reschedule all moves every overdue task and Undo brings them back", async ({ page }) => {
  test.setTimeout(60_000);
  await signIn(page);
  const today = todayIn();
  await page.goto("/board?tab=tasks");
  const before = await counts(page);
  await post(page, "/api/tasks", { title: "Late one", due_date: addDays(today, -3) });
  await post(page, "/api/tasks", { title: "Late two", due_date: addDays(today, -2) });
  await post(page, "/api/tasks", { title: "Due now", due_date: today });
  await post(page, "/api/tasks", { title: "Due soon", due_date: addDays(today, 4) });
  const after = await counts(page);
  expect(after.overdue).toBe(before.overdue + 2);
  expect(after.today).toBe(before.today + 1);
  expect(after.upcoming_14).toBe(before.upcoming_14 + 1);

  await page.reload();
  const detail = detailPane(page);
  // The Today tab counts overdue plus due today, the same set the Today list shows (todayCount).
  const views = detail.getByRole("group", { name: "Task views" });
  await expect(views.getByRole("button", { name: /^Today/ }).locator(".count")).toHaveText(String(after.overdue + after.today));
  await expect(views.getByRole("button", { name: /^Upcoming/ }).locator(".count")).toHaveText(String(after.upcoming_14));

  await openTaskView(page, "Overdue");
  await expect(detail.getByRole("row").filter({ hasText: "Late one" })).toBeVisible();
  await detail.getByRole("button", { name: "Reschedule all" }).click();
  await page.getByRole("group", { name: "Quick picks" }).getByRole("button", { name: /^Tomorrow/ }).click();
  await expect(toast(page)).toContainText(`${after.overdue} task`);
  await expect.poll(async () => (await counts(page)).overdue).toBe(0);
  await toast(page).getByRole("button", { name: "Undo" }).click();
  await expect.poll(async () => (await counts(page)).overdue).toBe(after.overdue);
  await expect(detail.getByRole("row").filter({ hasText: "Late one" })).toBeVisible();
});

test("a task row opens its steps and its drawer, and an edit in the drawer is saved", async ({ page }) => {
  test.setTimeout(60_000);
  await signIn(page);
  const made = await post(page, "/api/tasks", { title: "Paint the fence", due_date: todayIn(), steps: ["Sand it", "Two coats"] });
  await page.goto("/board?tab=tasks");
  const detail = detailPane(page);
  const row = detail.getByRole("row").filter({ hasText: "Paint the fence" });
  await row.getByRole("button", { name: /^Show the 2 steps of/ }).click();
  const steps = detail.getByRole("group", { name: "Steps of Paint the fence" });
  await expect(steps).toContainText("Sand it");
  await expect(steps).toContainText("Two coats");

  await row.getByRole("button", { name: "Paint the fence", exact: true }).click();
  const drawer = page.getByRole("dialog", { name: "Paint the fence" });
  await expect(drawer).toBeVisible();
  const title = drawer.getByLabel("Title");
  await title.fill("Paint the garden fence");
  await title.press("Enter");
  await expect.poll(async () => {
    const saved = await page.request.get(`/api/tasks/${made.id}`);
    return ((await saved.json()) as { title: string }).title;
  }).toBe("Paint the garden fence");
  await page.keyboard.press("Escape");
  await expect(detail.getByRole("row").filter({ hasText: "Paint the garden fence" })).toBeVisible();
});

test("Kanban: group by project, then Move to… another project with Undo", async ({ page }) => {
  test.setTimeout(60_000);
  await signIn(page);
  const orchard = await post(page, "/api/projects", { name: "Orchard" });
  const barn = await post(page, "/api/projects", { name: "Barn" });
  await post(page, "/api/tasks", { title: "Sweep the barn", project_id: barn.id });
  await post(page, "/api/tasks", { title: "Prune the apple tree", project_id: orchard.id });
  await page.goto("/board?tab=tasks&layout=kanban");
  const detail = detailPane(page);
  await detail.getByRole("combobox", { name: "Group by" }).click();
  await page.getByRole("option", { name: "Group by: Project" }).click();
  const from = detail.getByRole("region", { name: "Orchard", exact: true });
  const to = detail.getByRole("region", { name: "Barn", exact: true });
  const card = (column: Locator) => column.locator(".kcard", { hasText: "Prune the apple tree" });
  await expect(card(from)).toBeVisible();

  await card(from).getByRole("button", { name: "More for Prune the apple tree" }).click();
  await page.getByRole("menuitem", { name: "Barn", exact: true }).click();
  await expect(toast(page)).toContainText("moved to Barn");
  await expect(card(to)).toBeVisible();
  await expect(card(from)).toHaveCount(0);
  await toast(page).getByRole("button", { name: "Undo" }).click();
  await expect(card(from)).toBeVisible();
  await expect(card(to)).toHaveCount(0);
});

test("the Calendar: today boxed with its dots, today's agenda with a now line, a day note, and the week grid", async ({ page }) => {
  test.setTimeout(60_000);
  await signIn(page);
  const today = todayIn();
  for (const title of ["Cal one", "Cal two", "Cal three"]) await post(page, "/api/tasks", { title, due_date: today });
  await page.goto("/board?tab=calendar");
  const detail = detailPane(page);
  const name = dayText(today, { weekday: true });
  const day = detail.getByRole("grid").getByRole("button", { name: new RegExp(`^${name}, \\d+ tasks?$`) });
  await expect(day).toHaveClass(/is-today/);
  await expect(day.locator(".wcal__dot")).toHaveCount(3);   // three dots at most, then +N
  const agenda = detail.getByRole("region", { name: /^Agenda for Today/ });
  await expect(agenda).toContainText("Cal one");
  await expect(agenda.locator(".wcal__now")).toHaveCount(1);
  const note = agenda.getByRole("textbox", { name: "Add a day note" });
  await note.fill("Bin day, lanterns after dark");
  await note.press("Enter");
  await expect(agenda.locator(".dnote", { hasText: "Bin day, lanterns after dark" })).toBeVisible();
  await agenda.getByRole("button", { name: /Cal two/ }).click();
  await expect(page.getByRole("dialog", { name: "Cal two" })).toBeVisible();
  await page.keyboard.press("Escape");
  await detail.getByRole("group", { name: "Calendar span" }).getByRole("button", { name: "Week" }).click();
  await expect(page).toHaveURL(/cmode=week/);
  await expect(detail.getByRole("region", { name: "Task calendar" })).toBeVisible();
});

test("the Money expense line understands maths and +€ income, a star and a vendor", async ({ page }) => {
  test.setTimeout(60_000);
  await signIn(page);
  await post(page, "/api/projects", { name: "Reno" });
  await page.goto("/board?tab=money");
  const detail = detailPane(page);
  const line = detail.getByRole("combobox", { name: "New expense" });
  const rows = detail.getByRole("list", { name: "Expenses" }).getByRole("listitem");

  await line.fill("€2x31 paint /Reno");
  await expect(detail.locator(".quick-chip--read", { hasText: "€62.00 = 2×31" })).toBeVisible();
  await line.press("Enter");
  await expect(rows.filter({ hasText: "paint" })).toContainText("€62.00");

  await line.fill("+€500 refund /Reno");
  await expect(detail.locator(".quick-chip--read", { hasText: "Money in €500.00" })).toBeVisible();
  await line.press("Enter");
  await expect(rows.filter({ hasText: "refund" })).toContainText("money in");

  await line.fill("€12 lunch /Reno vendor:Mercadona *");
  await expect(detail.locator(".quick-chip--read", { hasText: "at Mercadona" })).toBeVisible();
  await expect(detail.locator(".quick-chip--read", { hasText: "Starred" })).toBeVisible();
  await line.press("Enter");
  const lunch = rows.filter({ hasText: "lunch" });
  await expect(lunch).toContainText("Mercadona");
  await expect(lunch.getByRole("button", { name: "Star the Reno expense" })).toHaveAttribute("aria-pressed", "true");
});

test("Money: edit an expense, delete it with Undo; By days and the period picker show the server's summary", async ({ page }) => {
  test.setTimeout(90_000);
  await signIn(page);
  const today = todayIn();
  const earlier = pastDayThisMonth(today);
  const project = await post(page, "/api/projects", { name: "Roof" });
  await post(page, "/api/money/expenses", { amount: "40", project_id: project.id, note: "tiles", spent_at: today });
  await post(page, "/api/money/expenses", { amount: "15", project_id: project.id, note: "nails", spent_at: earlier });
  await page.goto("/board?tab=money");
  const detail = detailPane(page);
  const rows = detail.getByRole("list", { name: "Expenses" }).getByRole("listitem");

  const tiles = rows.filter({ hasText: "tiles" });
  await tiles.getByRole("button", { name: "Edit the Roof expense" }).click();
  const edit = detail.locator(".xp--edit");
  await edit.getByLabel("Amount").fill("45,50");
  await edit.getByRole("button", { name: "Save", exact: true }).click();
  await expect(rows.filter({ hasText: "tiles" })).toContainText("€45.50");
  await rows.filter({ hasText: "tiles" }).getByRole("button", { name: "More for the Roof expense" }).click();
  await page.getByRole("menuitem", { name: "Delete", exact: true }).click();
  await expect(rows.filter({ hasText: "tiles" })).toHaveCount(0);
  await toast(page).getByRole("button", { name: "Undo" }).click();
  await expect(rows.filter({ hasText: "tiles" })).toContainText("€45.50");

  // By days: the strip, and a picked day lists that day's expenses.
  await detail.getByRole("group", { name: "Expenses view" }).getByRole("button", { name: "By days" }).click();
  await expect(detail.getByRole("group", { name: "Spending per day" })).toBeVisible();
  await detail.getByRole("group", { name: "Spending per day" }).getByRole("button", { name: new RegExp(`^${dayText(today, { weekday: true })}:`) }).click();
  await expect(detail.locator(".bydays__day")).toContainText("tiles");

  // The period picker: Today, then a custom range from the address; the summary is the server's count.
  await detail.getByRole("group", { name: "Expenses view" }).getByRole("button", { name: "List" }).click();
  await detail.getByRole("button", { name: /^Period: / }).click();
  await page.getByRole("dialog", { name: "Pick a period" }).getByRole("button", { name: "Today", exact: true }).click();
  const rangeToday = await (await page.request.get(`/api/money/range?from=${today}&to=${today}`)).json() as { summary: { count: number } };
  await expect(detail.locator(".rsum")).toContainText(`${rangeToday.summary.count} ${rangeToday.summary.count === 1 ? "expense" : "expenses"}`);
  await expect(detail.locator(".rsum")).toContainText("today");

  await page.goto(`/board?tab=money&range=custom&from=${earlier}&to=${today}`);
  const span = await (await page.request.get(`/api/money/range?from=${earlier}&to=${today}`)).json() as { summary: { count: number } };
  await expect(detail.getByRole("button", { name: /^Period: .+–/ })).toBeVisible();
  await expect(detail.locator(".rsum")).toContainText(`${span.summary.count} ${span.summary.count === 1 ? "expense" : "expenses"}`);
});

test("the money calendar's + adds an expense dated that day", async ({ page }) => {
  test.setTimeout(60_000);
  await signIn(page);
  const day = pastDayThisMonth(todayIn());
  const project = await post(page, "/api/projects", { name: "Trip" });
  await page.goto("/board?tab=money&mview=cal");
  const name = dayText(day, { weekday: true });
  const cell = page.locator(`[role=gridcell][data-day="${day}"]`);
  await cell.hover();
  await cell.getByRole("button", { name: `Add on ${name}` }).click();
  const adding = page.getByRole("dialog", { name: `Add expense on ${name}` });
  await adding.getByRole("combobox", { name: "New expense" }).fill("€7 kite /Trip");
  await adding.getByRole("combobox", { name: "New expense" }).press("Enter");
  await expect(toast(page)).toContainText(`on ${name}`);
  await expect.poll(async () => {
    const range = await page.request.get(`/api/money/range?from=${day}&to=${day}&project_id=${project.id}`);
    const body = (await range.json()) as { expenses: { description: string | null; spent_at: string }[] };
    return body.expenses.find((expense) => expense.description === "kite")?.spent_at;
  }).toBe(day);
});

test("the project page shows its header card, then its tasks and its money with their counts", async ({ page }) => {
  test.setTimeout(60_000);
  await signIn(page);
  const project = await post(page, "/api/projects", { name: "Cabin", budget: "1000", monthly_budget: "400" });
  await post(page, "/api/tasks", { title: "Order the logs", project_id: project.id, due_date: addDays(todayIn(), -1) });
  await post(page, "/api/money/expenses", { amount: "100", project_id: project.id, note: "stove", spent_at: todayIn() });
  await page.goto(`/board/projects/${project.id}`);
  const detail = detailPane(page);
  const card = detail.getByRole("region", { name: "Summary" });
  await expect(card.getByRole("heading", { name: "Cabin" })).toBeVisible();
  await expect(card.getByText("Active", { exact: true })).toBeVisible();
  await expect(card.locator(".p-stat")).toHaveCount(3);
  await expect(card.locator(".p-stat").nth(0)).toContainText("€900.00");
  await expect(card.locator(".p-stat").nth(0)).toContainText("left of €1,000.00");
  await expect(card.locator(".p-stat").nth(1)).toContainText("left of €400.00");
  await expect(card.locator(".p-stat").nth(2)).toContainText("1 overdue");
  const section = (title: string) => detail.locator(".project-section").filter({ has: page.getByRole("heading", { name: title, exact: true }) });
  await expect(section("Tasks").locator(".project-section__head .count")).toHaveText("1");
  await expect(section("Money").locator(".project-section__head .count")).toHaveText("1");
  await expect(section("Money").getByRole("combobox", { name: "New expense" }).first()).toBeVisible();
});
