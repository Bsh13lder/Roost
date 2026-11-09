import { expect, test } from "@playwright/test";
import { api, botIdFromUrl, createBot, detailPane, openFold, say, signIn } from "./helpers";

// The v1 chat feel, against ROOST_DESK=fake + fixtures/team-script.json ("Slowpoke", "Picker", "Stucky").
// Slowpoke's first model step waits three seconds, so what shows before it answers is the server's own doing.
const SLOW = { timeout: 20_000 };
const QUESTION = "Which day should I book the dentist?";
const STUCK_LINE = "Stuck on login.example: a sign-in page. Take control to clear it.";

test("a run shows words within a second, never dots alone", async ({ page }) => {
  await signIn(page);
  await createBot(page, "Slowpoke", "Takes its time");
  await say(page, "Slowpoke", "start the slow thing");
  // Words at once beside the bot's working robot: what it is doing (its first line, "Reading your message…"), or
  // the activity pill's "Thinking…" once its first step is in (owner, 2026-10-27: no "On it" text).
  await expect(detailPane(page).locator("svg.working-bot").first()).toBeVisible({ timeout: 1_000 });
  await expect(detailPane(page).getByText(/…$/).first()).toBeVisible({ timeout: 1_000 });
  await expect(detailPane(page).getByText("Slow answer one.")).toBeVisible(SLOW);
});

test("the composer stays usable and a second message joins the running reply (steer)", async ({ page }) => {
  test.setTimeout(60_000);
  await signIn(page);
  await page.goto("/");
  await page.locator("nav[aria-label='Chats']").getByRole("link", { name: /^Slowpoke\b/ }).click();
  const box = detailPane(page).getByPlaceholder("Message Slowpoke");
  await say(page, "Slowpoke", "first of two");
  await expect(box).toBeEnabled();
  await expect(detailPane(page).getByRole("button", { name: "Stop Slowpoke" })).toBeVisible();
  await say(page, "Slowpoke", "second of two");
  await expect(box).toBeEnabled();
  await expect(detailPane(page).getByText("Slow answer two.")).toBeVisible(SLOW);
  await expect(detailPane(page).getByText("Slow answer three.")).toBeVisible(SLOW);
  await expect(detailPane(page).getByText("Queued, I'll pick it up next")).toHaveCount(0);
});

test("an options card: the safe choice in words, your pick, Decisions with a Madrid date, then Forget", async ({ page }) => {
  test.setTimeout(60_000);
  await signIn(page);
  await createBot(page, "Picker", "Asks before it books");
  await say(page, "Picker", "book the dentist");
  const detail = detailPane(page);
  const card = detail.getByRole("group", { name: "Needs your choice" });
  await expect(card).toContainText(QUESTION, SLOW);
  await expect(card.getByRole("button", { name: /Tuesday.*Safe choice/ })).toBeVisible();
  await card.getByRole("button", { name: /^Monday$/ }).click();
  await expect(detail.getByText("Monday", { exact: true }).first()).toBeVisible(SLOW);
  await expect(detail.getByText("Booked for your pick.")).toBeVisible(SLOW);
  // Answered, the card is one line with a check (lead task 07), and stays so after a reload.
  await expect(detail.locator(".choice-done")).toContainText("You answered: Monday");
  await expect(detail.getByRole("group", { name: "Needs your choice" })).toHaveCount(0);
  await page.reload();
  await expect(detailPane(page).locator(".choice-done")).toContainText("You answered: Monday", SLOW);

  await detail.getByRole("link", { name: "Open Picker's profile" }).click();
  const panel = page.getByRole("complementary", { name: "Picker's profile" });
  await openFold(panel, "Decisions");
  const decisions = panel.getByRole("region", { name: "Decisions" });
  await expect(decisions).toContainText(QUESTION);
  await expect(decisions).toContainText("Monday");
  await expect(decisions).toContainText(/\d{2}:\d{2} Madrid/);
  await decisions.getByRole("button", { name: "Forget" }).click();
  await expect(decisions.getByText("No decisions yet.")).toBeVisible();
});

test("dismiss counts as No and the same question is not asked again", async ({ page }) => {
  test.setTimeout(60_000);
  await signIn(page);
  await page.goto("/");
  await page.locator("nav[aria-label='Chats']").getByRole("link", { name: /^Picker\b/ }).click();
  await say(page, "Picker", "book the dentist again");
  const detail = detailPane(page);
  const card = detail.getByRole("group", { name: "Needs your choice" });
  await expect(card).toContainText(QUESTION, SLOW);
  await card.getByRole("button", { name: "Dismiss" }).click();
  // Its next script step asks the very same question: the answer is already decided, so no second card opens.
  await expect(detail.getByText("Understood, I will not ask again.")).toBeVisible(SLOW);
  await expect(detail.getByRole("group", { name: "Needs your choice" })).toHaveCount(0);
});

test("Stuck says why and what to do, and keeps saying it after a reload", async ({ page }) => {
  test.setTimeout(60_000);
  await signIn(page);
  await createBot(page, "Stucky", "Checks my orders on shop sites");
  // On Mac Brave a sign-in wall is a plain Stuck card (a Linux computer's is the calmer Sign-in card, stuck.spec.ts).
  await api(page, "PATCH", `/api/bots/${botIdFromUrl(page)}`, { computer: "mac_brave" });
  await say(page, "Stucky", "check my orders on https://login.example/");
  const detail = detailPane(page);
  await expect(detail.locator(".chat-header").getByText(STUCK_LINE)).toBeVisible(SLOW);
  await page.reload();
  await expect(detail.locator(".chat-header").getByText(STUCK_LINE)).toBeVisible(SLOW);
  // Leave nothing waiting in My turn for the specs that follow.
  await detail.getByRole("group", { name: "Stuck on login.example" }).getByRole("button", { name: "Give up" }).click();
  await expect(detail.locator(".chat-header").getByText(STUCK_LINE)).toBeHidden(SLOW);
});

test("a tapback sticks after a reload", async ({ page }) => {
  await signIn(page);
  await page.goto("/");
  await page.locator("nav[aria-label='Chats']").getByRole("link", { name: /^Slowpoke\b/ }).click();
  const detail = detailPane(page);
  const message = detail.locator("li.message--bot").filter({ hasText: "Slow answer one." });
  await message.hover();
  await message.getByRole("button", { name: "React" }).click();
  await message.getByRole("button", { name: "Thumbs up" }).click();
  await expect(detail.getByRole("img", { name: "Reaction: Thumbs up" })).toBeVisible();
  await page.reload();
  await expect(detail.getByRole("img", { name: "Reaction: Thumbs up" })).toBeVisible(SLOW);
});
