import { expect, test } from "@playwright/test";
import { detailPane, openChat, say, signIn } from "./helpers";

test("the main bot is pinned from the start and creates the bots you ask for", async ({ page }) => {
  await signIn(page);
  // The main bot is pinned: it leads the pinned tiles as a Lensbot wearing its star, and is not in the chat list.
  const first = page.getByRole("list", { name: "Your bots" }).getByRole("link").first();
  await expect(first).toHaveAccessibleName(/^Chief\b/);
  await expect(first.locator(".robot__star")).toBeVisible();
  await expect(first.locator("svg.robot")).toHaveAttribute("data-shape", "mochi"); // its template's "classic" head, drawn as a Lensbot
  await expect(first.locator(".robot__eye")).toHaveCount(2);
  await expect(first.locator(".avatar-row__name")).toHaveText("Chief");
  await openChat(page, "Chief");
  const detail = detailPane(page);
  await say(page, "Chief", "make me a bot for HiMap SEO and one for HiMap Social");
  await expect(detail.getByRole("group", { name: "Created HiMap SEO" })).toBeVisible();
  await expect(detail.getByRole("group", { name: "Created HiMap Social" })).toBeVisible();
  // The main bot gave HiMap SEO a role: its card wears the SEO emblem; HiMap Social got none.
  await expect(detail.getByRole("group", { name: "Created HiMap SEO" }).locator("svg.robot")).toHaveAttribute("data-role", "seo");
  await expect(detail.getByRole("group", { name: "Created HiMap SEO" }).locator(".robot__emblem--seo")).toHaveCount(1);
  await expect(detail.getByRole("group", { name: "Created HiMap Social" }).locator(".robot__emblem")).toHaveCount(0);
  await expect(detail.getByText("Chief → HiMap SEO: List three quick SEO fixes for himap.app")).toBeVisible();
  await expect(detail.getByText(/HiMap SEO suggests: titles/)).toBeVisible();

  const chats = page.getByRole("navigation", { name: "Chats" });
  await expect(chats.getByRole("link", { name: /^HiMap SEO\b/ })).toBeVisible();
  page.once("dialog", (dialog) => void dialog.accept());
  await detail.getByRole("group", { name: "Created HiMap Social" }).getByRole("button", { name: "Undo" }).click();
  await expect(detail.getByText("Undone: HiMap Social was retired.")).toBeVisible();
  await page.goto("/");
  await expect(chats.getByRole("link", { name: /^HiMap Social\b/ })).toHaveCount(0);
});

test.describe("on a phone", () => {
  test.use({ viewport: { width: 390, height: 844 } });
  test("Home is one column, and a chat takes the whole screen", async ({ page }) => {
    await signIn(page);
    await expect(page.getByRole("navigation", { name: "Chats" })).toBeVisible();
    await openChat(page, "Chief");
    await expect(page.getByRole("navigation", { name: "Chats" })).toBeHidden();
    await detailPane(page).getByRole("link", { name: "Back to chats" }).click();
    await expect(page.getByRole("navigation", { name: "Chats" })).toBeVisible();
  });
});
