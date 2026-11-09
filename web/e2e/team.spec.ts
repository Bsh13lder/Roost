import { expect, test } from "@playwright/test";
import { createBot, detailPane, signIn } from "./helpers";

test("the Saturday room: Chief splits the work and posts one combined answer", async ({ page }) => {
  await signIn(page);
  await createBot(page, "Quill", "Writes lists and short notes");
  await page.goto("/");
  await page.getByRole("button", { name: "New", exact: true }).click();
  await page.getByRole("menuitem", { name: "New room" }).click();
  const dialog = page.getByRole("dialog", { name: "New room" });
  await dialog.getByLabel("Room name").fill("Saturday");
  // exact: profile.spec (earlier) made "Scout Two", which a substring match on "Scout" would also pick.
  for (const name of ["Chief", "Scout", "Quill"]) await dialog.getByRole("checkbox", { name, exact: true }).check();
  await expect(dialog.getByRole("combobox", { name: "Coordinator" })).toHaveText(/.+/);
  await dialog.getByRole("button", { name: "Create room" }).click();

  await page.waitForURL(/\/rooms\/[^/]+$/);
  const detail = detailPane(page);
  await expect(detail.getByRole("heading", { name: "Saturday", exact: true })).toBeVisible();
  const composer = detail.getByPlaceholder("Message the room… (@ to mention)");
  await composer.fill("plan Saturday groceries under 60 EUR");
  await composer.press("Enter");

  // The room's chat-row preview shows the newest of these lines too: stay in the detail pane.
  await expect(detail.getByText("Chief → Scout: Price a grocery basket under 60 EUR")).toBeVisible();
  await expect(detail.getByText("Chief → Quill: Write the shopping list")).toBeVisible();
  await expect(detail.getByText("Scout → Chief: Basket at Mercadona: 52 EUR.")).toBeVisible();
  await expect(detail.getByText("Quill → Chief: List: rice, eggs, tomatoes, chicken, fruit.")).toBeVisible();
  const answer = detail.getByRole("listitem").filter({ hasText: "Saturday plan: a 52 EUR basket at Mercadona" });
  await expect(answer).toHaveCount(1);
  await expect(answer).toContainText("Chief");
});
