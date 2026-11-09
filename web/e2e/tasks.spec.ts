import { expect, test } from "@playwright/test";
import { addDays, dayText, todayIn } from "../src/ui/date/dates";
import { detailPane, openBoard, openTaskView, signIn, workspacePill } from "./helpers";

// Redesign P3: quick-add a task with chips, open its drawer, add a step, a comment and an expense for the
// step, and close it with focus back on the row.
const PROJECT = "Plumbing";
const LINE = `Fix the leak tomorrow 9am /${PROJECT} €200 !high`;
const TASK = "Fix the leak";

test("quick add with chips, then the drawer: a step, a comment, an expense for the step", async ({ page }) => {
  test.setTimeout(60_000);
  const tomorrow = addDays(todayIn(), 1);
  await signIn(page);
  const origin = new URL(page.url()).origin;
  const created = await page.request.post("/api/projects", { data: { name: PROJECT }, headers: { Origin: origin } });
  expect(created.status()).toBe(201);
  const project = (await created.json()) as { id: string };

  await openBoard(page);
  const detail = detailPane(page);
  await workspacePill(page).fill(LINE);
  for (const chip of [`${dayText(tomorrow, { weekday: true })} 09:00`, `/${PROJECT}`, "€200.00", "!high"]) {
    await expect(detail.locator(".quick-chip--read", { hasText: chip })).toBeVisible();
  }
  const added = page.waitForRequest((r) => r.url().endsWith("/api/tasks") && r.method() === "POST");
  await workspacePill(page).press("Enter");
  expect((await added).postDataJSON()).toMatchObject({
    title: TASK, priority: "high", project_id: project.id, allocated_budget: "200.00",
  });
  await openTaskView(page, "Upcoming");   // due tomorrow, so not in Today
  const row = detail.getByRole("row").filter({ hasText: TASK });
  await expect(row.locator(".task-row__cell--project", { hasText: PROJECT })).toBeVisible();

  const title = row.getByRole("button", { name: TASK, exact: true });
  await title.click();
  await expect(page).toHaveURL(/[?&]task=/);
  const drawer = page.getByRole("dialog", { name: TASK });
  await expect(drawer.getByRole("button", { name: `Due, ${dayText(tomorrow, { weekday: true })}, 09:00` })).toBeVisible();

  await drawer.getByLabel("New step").fill("Buy a washer");
  await drawer.getByRole("button", { name: "Add step" }).click();
  await drawer.getByRole("checkbox", { name: "Done: Buy a washer" }).click();
  await expect(drawer.getByText("1 of 1 done")).toBeVisible();

  await drawer.getByLabel("New comment").fill("The plumber comes at 9");
  await drawer.getByRole("button", { name: "Comment", exact: true }).click();
  await expect(drawer.locator(".comment", { hasText: "The plumber comes at 9" }).getByText("You")).toBeVisible();

  // The expense line, with the task's project and the task fixed; For picks the step.
  await drawer.getByRole("combobox", { name: "For" }).click();
  await page.getByRole("option", { name: "Buy a washer" }).click();
  await drawer.getByLabel("New expense").fill("€12.50 washers");
  await drawer.getByRole("button", { name: "Add", exact: true }).click();
  // The slice figures (the server's numbers): Planned, Spent and Left, and the badge "left".
  const figures = drawer.getByRole("group", { name: "Planned, spent and left" });
  await expect(figures).toContainText("€200.00");
  await expect(figures).toContainText("€12.50");
  await expect(figures).toContainText("€187.50");
  await expect(drawer.locator(".step", { hasText: "Buy a washer" }).getByText("€12.50 spent")).toBeVisible();

  await page.keyboard.press("Escape");
  await expect(drawer).toHaveCount(0);
  await expect(page).not.toHaveURL(/[?&]task=/);
  await expect(row.getByRole("button", { name: /^Show the 1 steps of/ })).toContainText("1/1");
});
