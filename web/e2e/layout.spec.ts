import { expect, test, type Page } from "@playwright/test";
import { addDays, todayIn } from "../src/ui/date/dates";
import { detailPane, signIn } from "./helpers";

// The Board's layout on a small laptop window (1000×650, the sidebar beside it): the Board fills the main area,
// the Month calendar is seven days across, nothing scrolls sideways, and a sidebar whose bots are all pinned
// never claims there are no chats. The Board is shared with the other specs, so this spec adds its own records only.
const LAPTOP = { width: 1000, height: 650 };
const MIN_SHARE = 0.85;
const DAYS_PER_WEEK = 7;

interface Bot { id: string; pinned: boolean; is_primary: boolean }

const originOf = (page: Page): string => `http://127.0.0.1:${new URL(page.url()).port || "80"}`;

async function send(page: Page, method: "POST" | "PUT", path: string, data: object): Promise<void> {
  const response = await page.request.fetch(path, { method, data, headers: { Origin: originOf(page) } });
  expect(response.ok(), `${method} ${path}: ${await response.text()}`).toBe(true);
}

async function noSidewaysScroll(page: Page): Promise<void> {
  const overflow = await page.evaluate(() => {
    const doc = document.documentElement;
    const detail = document.querySelector(".app-shell__detail");
    return { page: doc.scrollWidth - doc.clientWidth, detail: detail ? detail.scrollWidth - detail.clientWidth : 0 };
  });
  expect(overflow).toEqual({ page: 0, detail: 0 });
}

async function share(page: Page, selector: string): Promise<number> {
  const main = await detailPane(page).boundingBox();
  const content = await page.locator(selector).first().boundingBox();
  if (!main || !content) throw new Error(`no box for main or ${selector}`);
  return content.width / main.width;
}

test.use({ viewport: LAPTOP });

test("at 1000px the Month calendar is seven days across and the Workspace fills the main area", async ({ page }) => {
  test.setTimeout(60_000);
  await signIn(page);
  const today = todayIn();
  await send(page, "POST", "/api/tasks", { title: "Layout check today", due_date: today });
  await send(page, "POST", "/api/tasks", { title: "Layout check tomorrow", due_date: addDays(today, 1) });

  await page.goto("/board?tab=calendar");
  const grid = detailPane(page).getByRole("grid");
  await expect(grid).toBeVisible();
  const firstWeek = grid.getByRole("row").nth(1).getByRole("gridcell");   // the first row holds the weekday names
  await expect(firstWeek).toHaveCount(DAYS_PER_WEEK);
  const boxes = await firstWeek.evaluateAll((cells) => cells.map((cell) => cell.getBoundingClientRect()).map((r) => ({ x: r.x, y: r.y, w: r.width })));
  expect(new Set(boxes.map((box) => Math.round(box.y))).size, "the week's days share one line").toBe(1);
  for (let i = 1; i < boxes.length; i += 1) expect(boxes[i].x).toBeGreaterThan(boxes[i - 1].x);
  expect(Math.min(...boxes.map((box) => box.w))).toBeGreaterThan(60);
  expect(await share(page, ".wcal__grid")).toBeGreaterThanOrEqual(MIN_SHARE);
  await noSidewaysScroll(page);

  for (const url of ["/board?tab=tasks", "/board?tab=tasks&layout=kanban", "/board?tab=money"]) {
    await page.goto(url);
    await expect(detailPane(page).locator(".board-wrap")).toBeVisible();
    expect(await share(page, ".board-wrap > *"), url).toBeGreaterThanOrEqual(MIN_SHARE);
    await noSidewaysScroll(page);
  }
});

test("at 1000px a task's title has room in the List", async ({ page }) => {
  await signIn(page);
  const title = "Layout check a title that needs room";
  await send(page, "POST", "/api/tasks", { title, due_date: todayIn() });
  await page.goto("/board?tab=tasks");
  const name = detailPane(page).getByRole("row").filter({ hasText: title }).locator(".task-row__open .t");
  await expect(name).toBeVisible();
  const box = await name.boundingBox();
  expect(box?.width ?? 0).toBeGreaterThan(200);
  await noSidewaysScroll(page);
});

test("with every bot pinned the sidebar never says No chats yet", async ({ page }) => {
  await signIn(page);
  const bots = (await (await page.request.get("/api/bots")).json()) as Bot[];
  expect(bots.length).toBeGreaterThan(0);
  const unpinned = bots.filter((bot) => !bot.pinned && !bot.is_primary);
  try {
    for (const bot of unpinned) await send(page, "PUT", `/api/bots/${bot.id}/pin`, { pinned: true });
    await page.goto("/");
    await expect(page.getByRole("list", { name: "Your bots" })).toBeVisible();
    await expect(page.getByText("No chats yet.")).toHaveCount(0);
  } finally {
    for (const bot of unpinned) await send(page, "PUT", `/api/bots/${bot.id}/pin`, { pinned: false });
  }
});
