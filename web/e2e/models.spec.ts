import { expect, test, type Page } from "@playwright/test";
import { detailPane, openChat, openProfilePage, say, signIn } from "./helpers";

// Models and helpers, against fixtures/team-script.json ("Chief"'s suggest_model, "Scout"'s send_helpers and
// "Scout/helper-1" and "-2") and fixtures/models-page.html, the public page the gateway checks at once in scripted
// mode (it lists claude-opus-6 as new). computer.spec (earlier, alphabetically) made Scout.
// The script is consumed in order, so these tests run after main-bot.spec and look.spec and before team.spec.
test.describe.configure({ mode: "serial" });

async function openInfo(page: Page, name: string) {
  await openChat(page, name);
  await detailPane(page).getByRole("link", { name: `Open ${name}'s profile` }).click();
  const panel = page.getByRole("complementary", { name: `${name}'s profile` });
  await openProfilePage(panel, "Settings");
  return panel;
}

test("pick Opus 5.5 and High in Info and see them after a reload", async ({ page }) => {
  await signIn(page);
  const info = await openInfo(page, "Scout");
  await info.getByRole("combobox", { name: "Model" }).click();
  await page.getByRole("option", { name: "Opus 5.5" }).click();
  await expect(info.getByRole("combobox", { name: "Model" })).toHaveText(/Opus 5\.5/);
  await info.getByRole("combobox", { name: "Effort" }).click();
  await page.getByRole("option", { name: "High", exact: true }).click();
  await expect(info.getByRole("combobox", { name: "Effort" })).toHaveText(/High/);

  await page.reload();
  const again = page.getByRole("complementary", { name: "Scout's profile" });
  await expect(again.getByRole("combobox", { name: "Model" })).toHaveText(/Opus 5\.5/);
  await expect(again.getByRole("combobox", { name: "Effort" })).toHaveText(/High/);
});

test("the main bot's card: Switch changes the bot, and Info shows the new model", async ({ page }) => {
  await signIn(page);
  await openChat(page, "Chief");
  const detail = detailPane(page);
  await say(page, "Chief", "which model should Scout use for price hunts?");
  const card = detail.getByRole("group", { name: "Switch Scout to Fable 5.2" });
  await expect(card).toBeVisible();
  await expect(card).toContainText("Long price hunts need deeper reasoning.");
  await card.getByRole("button", { name: "Switch", exact: true }).click();
  await expect(detail.getByText("Switched Scout to Fable 5.2 at high effort")).toBeVisible();

  const info = await openInfo(page, "Scout");
  await expect(info.getByRole("combobox", { name: "Model" })).toHaveText(/Fable 5\.1/);
});

test("the new-model banner: Try it opens a bot's Info with the list open, and Dismiss survives a reload", async ({ page }) => {
  await signIn(page);
  const banner = page.getByRole("status").filter({ hasText: "New model: Opus 6" });
  await expect(banner).toBeVisible();
  await expect(banner.getByRole("button", { name: "Try it" })).toHaveCount(0); // folded to one row at first
  await banner.getByRole("button", { name: "Show new model" }).click();
  await banner.getByRole("button", { name: "Try it" }).click();
  await page.getByRole("menuitem", { name: "Scout", exact: true }).click();
  await page.waitForURL(/\/bots\/[^/?]+\?.*try=claude-opus-6/);
  await expect(page.getByRole("listbox")).toBeVisible();
  await expect(page.getByRole("option", { name: "Opus 6 · New" })).toBeVisible();
  await page.keyboard.press("Escape");

  await banner.getByRole("button", { name: "Dismiss" }).click();
  await expect(banner).toHaveCount(0);
  await page.reload();
  await expect(page.getByText("New model: Opus 6")).toHaveCount(0);
});

test("Scout sends two helpers: the reply says so and no helper text shows in the chat", async ({ page }) => {
  await signIn(page);
  await openChat(page, "Scout");
  const detail = detailPane(page);
  await say(page, "Scout", "find the bakery's hours and a loaf's price");
  await expect(detail.getByText("Both helpers are back: the bakery opens at 08:00")).toBeVisible();
  // The step is in the activity pill: its sheet says how many helpers went, never their tasks or reports.
  await expect(detail.getByTestId("activity-pill")).toHaveCount(0, { timeout: 10_000 });
  await detail.getByTestId("activity-line").last().click();
  await expect(page.getByRole("dialog", { name: "What Scout did" })).toContainText("Sent 2 helpers");
  await expect(page.getByText("HELPER-ONE-REPORT")).toHaveCount(0);
  await expect(page.getByText("HELPER-TWO-REPORT")).toHaveCount(0);
});
