import { expect, test } from "@playwright/test";
import { api, botIdFromUrl, createBot, detailPane, openProfilePage, signIn } from "./helpers";

// A new bot starts on its Linux computer; this one is switched to Mac Brave (its own Brave window), and this path checks the screenshot box and the old Take control.
// The Linux computer, its live screen and the full-screen Take control are in computer-live.spec.ts and stuck.spec.ts.
test("the Computer tab on a Mac Brave bot: asleep, Open it, Take control and Give it back", async ({ page }) => {
  await signIn(page);
  await createBot(page, "Scout", "Finds prices and opening hours");
  await api(page, "PATCH", `/api/bots/${botIdFromUrl(page)}`, { computer: "mac_brave" });
  await page.reload();
  await detailPane(page).getByRole("link", { name: "Open Scout's profile" }).click();
  const detail = page.getByRole("complementary", { name: "Scout's profile" });
  await openProfilePage(detail, "Computer");
  await expect(detail.getByRole("heading", { name: "Computer is asleep" })).toBeVisible();
  await detail.getByRole("button", { name: "Open it" }).click();
  await expect(detail.getByRole("img", { name: "Scout’s screen" })).toBeVisible();
  await detail.getByRole("button", { name: "Take control" }).click();
  await expect(detail.getByText(/You have control/)).toBeVisible();
  await detail.getByRole("button", { name: "Give it back" }).click();
  await expect(detail.getByRole("button", { name: "Take control" })).toBeVisible();
  await expect(detail.getByRole("heading", { name: "About this computer" })).toBeVisible();
});
