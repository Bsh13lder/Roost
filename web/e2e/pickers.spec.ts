import { expect, test } from "@playwright/test";
import { dateLabel } from "../src/components/projects/projects";
import { addDays, dayText, todayIn } from "../src/ui/date/dates";
import { detailPane, openBoard, openTaskView, signIn, startNewProject, workspacePill } from "./helpers";

// The date pickers (redesign P1), from a browser far from Madrid: every pick must still be Madrid's
// day and Madrid's clock. The expected days come from the same helpers the web uses, on Madrid time.
test.use({ timezoneId: "America/Los_Angeles" });

const TASK = "Water the plants";
const PROJECT = "Garden plan";

test("a task due at a picked day and time, a project start typed in words, an expense's day typed in the line", async ({ page }) => {
  test.setTimeout(60_000);
  const today = todayIn();
  const tomorrow = addDays(today, 1);
  await signIn(page);
  await openBoard(page);
  const detail = detailPane(page);

  // A task (redesign P3: its due is picked in the drawer): Tomorrow and 09:00 go out as Madrid's day and
  // wall time, and come back the same.
  await workspacePill(page).fill(TASK);
  await workspacePill(page).press("Enter");
  await openTaskView(page, "Someday");   // a task with no day is under Someday, not Today
  await detail.getByRole("row").filter({ hasText: TASK }).getByRole("button", { name: TASK, exact: true }).click();
  const drawer = page.getByRole("dialog", { name: TASK });
  // Due applies at once through the reschedule popover: a time typed first, then a quick pick (the day).
  await drawer.getByRole("button", { name: /^Due, / }).click();
  await page.getByLabel("Time (optional)").fill("09:00");
  const saved = page.waitForRequest((r) => /\/api\/tasks\/[^/]+$/.test(r.url()) && r.method() === "PATCH");
  await page.getByRole("group", { name: "Quick picks" }).getByRole("button", { name: /^Tomorrow/ }).click();
  expect((await saved).postDataJSON()).toMatchObject({ due_date: `${tomorrow}T09:00` });
  await expect(drawer.getByRole("button", { name: `Due, ${dayText(tomorrow, { weekday: true })}, 09:00` })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(drawer).toHaveCount(0);

  // A project: "tomorrow", typed, is read by the gateway and saved as Madrid's day.
  // New project is in the project chips' menu (the Workspace); its form opens in a sheet.
  await startNewProject(page);
  const form = page.getByRole("form", { name: "New project", exact: true });
  await form.getByLabel("Name", { exact: true }).fill(PROJECT);
  await form.getByLabel("Starts", { exact: true }).fill("tomorrow");
  await expect(form.locator(".date-field__preview--read")).toHaveCount(1);
  await form.getByRole("button", { name: "Create project", exact: true }).click();
  await expect(form).toHaveCount(0);
  await detail.getByRole("link", { name: "Open project ›", exact: true }).click();   // the new project is picked
  await expect(detail.getByText(`Starts ${dateLabel(tomorrow)}`)).toBeVisible();

  // An expense: "yesterday", typed in the expense line, is read by the gateway as Madrid's yesterday.
  await openBoard(page);
  await detail.getByRole("button", { name: "Projects and money" }).click();   // All money: the old Money page
  await page.getByRole("menuitem", { name: "All money" }).click();
  const line = detail.getByRole("combobox", { name: "New expense", exact: true });
  await line.fill("€9,90 Seeds yesterday");
  const logged = page.waitForRequest((r) => r.url().endsWith("/api/money/expenses") && r.method() === "POST");
  await line.press("Enter");
  expect((await logged).postDataJSON()).toMatchObject({ amount: "9.90", spent_at: addDays(today, -1) });
});
