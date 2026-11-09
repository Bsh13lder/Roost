import { expect, test, type Page } from "@playwright/test";
import { createBot, detailPane, openFold, openProfilePage, say, signIn } from "./helpers";

// Routines and the Plan (routines plan, Task 18), against ROOST_DESK=fake + fixtures/team-script.json
// ("Clock", "Proposer", "Asker", "Diarist") and a scripted gateway whose scheduler ticks every two seconds
// (ROOST_SCHEDULER_TICK_SECONDS, honoured only in scripted mode).
const SLOW = { timeout: 20_000 };

async function openInfo(page: Page, name: string) {
  await detailPane(page).getByRole("link", { name: `Open ${name}'s profile` }).click();
  return page.getByRole("complementary", { name: `${name}'s profile` });
}

const chatsPane = (page: Page) => page.getByRole("complementary", { name: "Chats pane" });

test("make a routine, run it now: a Report in the chat, its run log, and Done in History", async ({ page }) => {
  test.setTimeout(60_000);
  await signIn(page);
  await createBot(page, "Clock", "Checks things on a schedule");
  const chatUrl = page.url().split("?")[0];
  const panel = await openInfo(page, "Clock");
  await openFold(panel, "Routines and questions");
  const routines = panel.getByRole("region", { name: "Routines" });
  await routines.getByRole("button", { name: "New routine" }).click();
  const sheet = page.getByRole("dialog", { name: "New routine" });
  await sheet.getByLabel("Name").fill("Daily check");
  await sheet.getByLabel("What to do").fill("Look at my tasks and say what matters.");
  await sheet.getByRole("button", { name: "Save" }).click();
  await expect(routines.locator(".routine-row__name")).toHaveText("Daily check", SLOW);

  await routines.getByRole("button", { name: "More for Daily check" }).click();
  await page.getByRole("menuitem", { name: "Run now" }).click();
  await routines.getByRole("button", { name: "Yes, run it now" }).click();
  const report = detailPane(page).getByRole("article", { name: /^Report:/ });
  await expect(report).toContainText("Routine checked: nothing new today.", SLOW);

  await report.getByRole("link", { name: "Open run log" }).click();
  await expect(detailPane(page).getByRole("heading", { name: "Daily check · run log" })).toBeVisible(SLOW);

  await page.goto(`${chatUrl}?panel=plan`);
  const again = page.getByRole("complementary", { name: "Clock's profile" });
  await again.getByRole("button", { name: "More for Daily check" }).click();
  await page.getByRole("menuitem", { name: "History" }).click();
  const history = page.getByRole("dialog", { name: /^History/ });
  await expect(history.getByText("Done")).toBeVisible(SLOW);
});

test("a bot proposes a routine: the card in the chat, the row in My turn, and Approve lists it", async ({ page }) => {
  test.setTimeout(60_000);
  await signIn(page);
  await createBot(page, "Proposer", "Suggests routines");
  await say(page, "Proposer", "set up a morning routine");
  const card = detailPane(page).getByRole("region", { name: "New routine" });
  await expect(card).toContainText("Morning check", SLOW);
  await page.goto("/");
  await expect(chatsPane(page).getByRole("region", { name: "My turn" })
    .getByRole("link", { name: "Proposer · New routine · Morning check" })).toBeVisible(SLOW);

  await chatsPane(page).getByRole("navigation", { name: "Chats" }).getByRole("link", { name: /^Proposer\b/ }).click();
  await detailPane(page).getByRole("region", { name: "New routine" }).getByRole("button", { name: "Approve" }).click();
  await expect(detailPane(page).getByText("Approved", { exact: true })).toBeVisible(SLOW);
  const panel = await openInfo(page, "Proposer");
  await openFold(panel, "Routines and questions");
  await expect(panel.getByRole("region", { name: "Routines" }).locator(".routine-row__name")).toHaveText("Morning check", SLOW);
});

test("a noted question shows in My turn, and your answer comes back as your message", async ({ page }) => {
  test.setTimeout(60_000);
  await signIn(page);
  await createBot(page, "Asker", "Wonders about things");
  await say(page, "Asker", "draft my monthly invoice");
  await expect(detailPane(page).getByText("I noted a question and carried on with PDF.")).toBeVisible(SLOW);
  await page.goto("/");
  const row = chatsPane(page).getByRole("region", { name: "My turn" })
    .getByRole("link", { name: "Asker · Which invoice format do you prefer?" });
  await expect(row).toBeVisible(SLOW);
  await row.click();
  const askerPanel = page.getByRole("complementary", { name: "Asker's profile" });
  await openFold(askerPanel, "Question book");
  const book = askerPanel.getByRole("region", { name: "Questions" });
  await expect(book).toContainText("Carrying on with: PDF", SLOW);
  await book.getByLabel("Your answer to: Which invoice format do you prefer?").fill("Excel sheets please");
  await book.getByRole("button", { name: "Answer" }).click();
  await expect(detailPane(page).getByText("Excel sheets please").first()).toBeVisible(SLOW);
});

test("the Plan: a bot's item on the Kanban, dragged to Done, in the Calendar, and edited as text", async ({ page }) => {
  test.setTimeout(60_000);
  await signIn(page);
  await createBot(page, "Diarist", "Keeps a plan");
  await say(page, "Diarist", "plan my day");
  await expect(detailPane(page).getByText("It is on my Plan.")).toBeVisible(SLOW);
  const panel = await openInfo(page, "Diarist");
  await openProfilePage(panel, "Plan & routines");
  const views = panel.getByRole("group", { name: "Plan view" });
  await views.getByRole("button", { name: "Kanban" }).click();
  const card = panel.locator(".kcard").filter({ hasText: "Water the ferns" });
  await expect(card).toBeVisible(SLOW);
  // Native drag and drop, driven by its three events (a headless browser's real drag is not reliable).
  const transfer = await page.evaluateHandle(() => new DataTransfer());
  const done = panel.getByRole("region", { name: "Done" });
  await card.dispatchEvent("dragstart", { dataTransfer: transfer });
  await done.dispatchEvent("dragover", { dataTransfer: transfer });
  await done.dispatchEvent("drop", { dataTransfer: transfer });
  await expect(panel.getByRole("region", { name: "Done" }).getByText("Water the ferns")).toBeVisible(SLOW);

  await views.getByRole("button", { name: "Calendar" }).click();
  await expect(panel.getByRole("list", { name: "No date" }).getByText("Water the ferns")).toBeVisible();

  await views.getByRole("button", { name: "Text" }).click();
  const text = panel.getByRole("textbox", { name: "Plan text" });
  await expect(text).toHaveValue(/Water the ferns/);
  await text.fill(`${await text.inputValue()}\n- [ ] Call the plumber\n`);
  await panel.getByRole("button", { name: "Save" }).click();
  await expect(panel.getByText("Saved", { exact: true })).toBeVisible(SLOW);
  await views.getByRole("button", { name: "Kanban" }).click();
  await expect(panel.getByRole("region", { name: "Planned" }).getByText("Call the plumber")).toBeVisible(SLOW);
});

test("a task whose reminder passed a minute ago gets a Reminder Report after one scheduler tick", async ({ page }) => {
  test.setTimeout(60_000);
  await signIn(page);
  const origin = new URL(page.url()).origin;
  const created = await page.request.post("/api/tasks", {
    headers: { Origin: origin },
    data: { title: "Pay the plumber", reminder_at: new Date(Date.now() - 60_000).toISOString() },
  });
  expect(created.ok(), await created.text()).toBe(true);
  const bots = (await (await page.request.get("/api/bots")).json()) as { id: string; is_primary: boolean }[];
  await page.goto(`/bots/${bots.find((bot) => bot.is_primary)!.id}`);
  // The task also has its advance reminders, which have passed as well: each posts its own Report.
  await expect(detailPane(page).getByRole("article", { name: /^Report: Reminder: Pay the plumber/ }).first()).toBeVisible(SLOW);
});
