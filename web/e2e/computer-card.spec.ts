import { expect, test, type Page } from "@playwright/test";
import { api, botIdFromUrl, createBot, detailPane, say, signIn, useLinuxComputer } from "./helpers";

// The computer card (docs/plans/2026-10-23-roost-computer-card.md), against ROOST_DESK=fake with
// ROOST_FAKE_SCREEN=shop: while the Shopper script (fixtures/team-script.json) works its computer, its reply shows
// one compact computer line (the site, the newest step, its number; never the screen: owner, 2026-10-26) under its
// activity pill; when the run parks on Buy now, the pill folds into one line that opens the sheet with the steps,
// Open computer and Take control, and no screen stays in the chat. CARD_SHOTS=<dir> also saves screenshots there,
// at a desktop and a phone width.
const SLOW = { timeout: 30_000 };
const SHOTS = process.env.CARD_SHOTS;
const DESKTOP = { width: 1440, height: 900 };
const PHONE = { width: 390, height: 844 };

async function shot(page: Page, name: string) {
  if (!SHOTS) return;
  for (const [label, size] of [["1440", DESKTOP], ["390", PHONE]] as const) {
    await page.setViewportSize(size);
    await page.waitForTimeout(250);
    await page.screenshot({ path: `${SHOTS}/${name}-${label}.png` });
  }
  await page.setViewportSize(DESKTOP);
}

test("the computer line shows where a working bot is, folds into a line, and opens the steps", async ({ page }) => {
  test.setTimeout(180_000);
  await page.setViewportSize(DESKTOP);
  await signIn(page);
  await createBot(page, "Shopper", "Shops for me on my sites");
  const botId = botIdFromUrl(page);
  await useLinuxComputer(page, botId);
  await api(page, "PUT", `/api/bots/${botId}/approval`, { mode: "ask", ask_topics: [] });
  await page.reload();
  const detail = detailPane(page);

  await say(page, "Shopper", "Find 'blue mug' on shop.test");
  const card = detail.getByTestId("computer-card");
  await expect(card).toBeVisible(SLOW);
  await expect(card).toContainText(/Step \d+/);
  await expect(card.locator("canvas")).toHaveCount(0);
  await shot(page, "card-live");

  // The run parks on Buy now (an Ask card): the bot is no longer On it, and the pill folds into its line.
  const line = detail.getByRole("button", { name: /Worked for .+ · \d+ steps · shop.test/ });
  await expect(line).toBeVisible(SLOW);
  await expect(card).toHaveCount(0);
  // No screen stays in the chat, the newest run included.
  await expect(detail.getByTestId("computer-kept")).toHaveCount(0);
  await line.scrollIntoViewIfNeeded();
  await shot(page, "card-folded");

  await line.click();
  const sheet = page.getByRole("dialog", { name: "What Shopper did" });
  await expect(sheet).toBeVisible(SLOW);
  await expect(sheet.getByRole("region", { name: "Steps" })).toContainText("Clicked on the screen");
  await expect(sheet.getByRole("button", { name: "Take control" })).toBeVisible();
  await shot(page, "card-sheet");
  await sheet.getByRole("button", { name: "Open computer" }).click();
  await expect(page).toHaveURL(/panel=computer/);
});
