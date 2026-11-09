import { expect, test, type Page } from "@playwright/test";
import { signIn } from "./helpers";

// The Workspace on a phone (G14, app restructure), 390 × 844: nothing scrolls sideways but the things meant to
// (the Kanban's columns, the project chips), the Kanban snaps column by column, the Calendar is a month of dots over
// the day's agenda, and Tasks · Notes · Calendar with the pill sit in a bottom bar.
test.use({ viewport: { width: 390, height: 844 }, hasTouch: true });

const PROJECT = "Phone house";
const ORIGIN = "http://127.0.0.1";

async function post(page: Page, path: string, data: object): Promise<{ id: string }> {
  const origin = `${ORIGIN}:${new URL(page.url()).port || "80"}`;
  const response = await page.request.post(path, { data, headers: { Origin: origin } });
  expect(response.ok(), await response.text()).toBe(true);
  return response.json() as Promise<{ id: string }>;
}

// The page itself does not scroll sideways: its width is the screen's.
async function expectNoSideScroll(page: Page): Promise<void> {
  const widths = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, client: document.documentElement.clientWidth }));
  expect(widths.scroll).toBeLessThanOrEqual(widths.client);
}

test("Tasks, All money and a project page do not scroll sideways; Kanban swipes; the Calendar has the day's agenda", async ({ page }) => {
  test.setTimeout(90_000);
  await signIn(page);
  const project = await post(page, "/api/projects", { name: PROJECT, budget: "2000", monthly_budget: "500" });
  await post(page, "/api/tasks", { title: "Paint the long hallway and the stairs, then the whole upstairs landing", project_id: project.id, due_date: "today" });
  await post(page, "/api/tasks", { title: "Buy tiles", project_id: project.id });
  await post(page, "/api/money/expenses", { amount: "45", project_id: project.id, note: "Paint and brushes from the shop on the corner" });

  await page.goto("/board?tab=tasks");
  await expect(page.getByRole("row").filter({ hasText: "Paint the long hallway" })).toBeVisible();
  await expectNoSideScroll(page);

  // Kanban: the columns are swipeable pages that snap.
  await page.goto("/board?tab=tasks&layout=kanban");
  const board = page.getByRole("group", { name: "Kanban board" });
  await expect(board).toBeVisible();
  expect(await board.evaluate((el) => getComputedStyle(el).scrollSnapType)).toContain("mandatory");
  const columns = board.locator(".kcol");
  expect(await columns.count()).toBeGreaterThan(1);
  expect(await board.evaluate((el) => el.scrollWidth > el.clientWidth)).toBe(true);
  await expectNoSideScroll(page);
  const second = columns.nth(1);
  await second.scrollIntoViewIfNeeded();
  await board.evaluate((el) => el.scrollBy({ left: 200 }));
  await expect.poll(() => board.evaluate((el) => el.scrollLeft)).toBeGreaterThan(0);

  // Calendar (the old ?layout=calendar link lands there): a month of dots, the picked day's agenda under it.
  await page.goto("/board?tab=tasks&layout=calendar");
  await expect(page.getByRole("grid")).toHaveCount(1);
  await expect(page.getByRole("region", { name: /^Agenda for Today/ })).toBeVisible();
  await expect(page.getByRole("region", { name: /^Agenda/ }).getByText("Paint the long hallway", { exact: false })).toBeVisible();
  await expectNoSideScroll(page);

  await page.goto("/board?tab=money");
  await expect(page.getByRole("combobox", { name: "New expense" }).first()).toBeVisible();
  await expectNoSideScroll(page);
  await page.goto("/board?tab=money&mview=cal");
  await expect(page.getByRole("region", { name: "Expense agenda" })).toBeVisible();
  await expectNoSideScroll(page);

  await page.goto(`/board/projects/${project.id}`);
  await expect(page.getByRole("heading", { name: PROJECT })).toBeVisible();
  await expectNoSideScroll(page);
  await page.goto(`/board/projects/${project.id}?tab=money`);   // an old link: tasks and money are one page now
  await expect(page.getByRole("region", { name: "Top-ups" })).toBeVisible();
  await expectNoSideScroll(page);

  // The bottom bar: the pill and Tasks · Notes · Calendar stay in view at the bottom of the screen.
  await page.goto("/board?tab=tasks");
  const pill = page.getByRole("combobox", { name: "Add or find anything" });
  const sections = page.getByRole("group", { name: "Workspace sections" });
  await expect(pill).toBeInViewport();
  await expect(sections.getByRole("button", { name: "Calendar" })).toBeInViewport();
  const bar = await sections.boundingBox();
  expect(bar?.y ?? 0).toBeGreaterThan(844 / 2);
  await expectNoSideScroll(page);
});
