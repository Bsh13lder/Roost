import { expect, test } from "@playwright/test";
import { createBot, detailPane, openChat, openProfilePage, signIn } from "./helpers";

// Polish R1, the Grok-feel shell: the fixed sidebar, the profile as a panel beside the chat, and the composer pill.
const NAME = "Ivy";

test("the sidebar: search and + on top, your bots' tiles, chats under a label, your initials and Board at the bottom", async ({ page }) => {
  await signIn(page);
  await createBot(page, NAME, "Keeps the house in order");
  const side = page.getByRole("complementary", { name: "Chats pane" });
  await expect(side.getByRole("searchbox", { name: "Search chats" })).toBeVisible();
  await expect(side.getByRole("button", { name: "New", exact: true })).toBeVisible();
  await expect(side.getByRole("link", { name: "Workspace", exact: true })).toBeVisible();
  const yourBots = side.getByRole("list", { name: "Your bots" });
  await expect(yourBots).toBeVisible();
  await expect(yourBots.getByRole("link").first()).toHaveAccessibleName(/^Chief\b/);
  await expect(yourBots.locator(".avatar-row__name").first()).toBeVisible();
  // Your initials open Settings (restructure slice 3): grouped cards, Sign out last.
  await side.getByRole("button", { name: "Settings", exact: true }).click();
  const settings = page.getByRole("dialog", { name: "Settings" });
  await expect(settings.getByRole("region", { name: "Appearance" })).toBeVisible();
  await expect(settings.getByRole("button", { name: "Sign out" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(settings).toHaveCount(0);

  await openChat(page, NAME);
  await detailPane(page).getByRole("link", { name: `Open ${NAME}'s profile` }).click();
  const panel = page.getByRole("complementary", { name: `${NAME}'s profile` });
  await panel.getByRole("button", { name: "Edit", exact: true }).click();
  await panel.getByRole("button", { name: "Add a label" }).click();
  await page.getByRole("textbox", { name: "Label" }).fill("Home");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  const chats = side.getByRole("navigation", { name: "Chats" });
  await expect(chats.getByRole("heading", { name: "Home", exact: true })).toBeVisible();
  const group = chats.getByRole("region", { name: "Home" });
  await expect(group.getByRole("link", { name: new RegExp(`^${NAME}\\b`) })).toBeVisible();

  await side.getByRole("searchbox", { name: "Search chats" }).fill(NAME);
  await expect(chats.getByRole("link", { name: new RegExp(`^${NAME}\\b`) })).toBeVisible();
  await expect(side.getByRole("list", { name: "Your bots" })).toHaveCount(0);
});

test("pinning moves a bot from the chat list to the pinned tiles, and Unpin brings it back", async ({ page }) => {
  await signIn(page);
  const side = page.getByRole("complementary", { name: "Chats pane" });
  const chats = side.getByRole("navigation", { name: "Chats" });
  const row = side.getByRole("list", { name: "Your bots" });
  await chats.getByRole("button", { name: `${NAME} menu` }).click({ force: true });
  await page.getByRole("menuitem", { name: "Pin", exact: true }).click();
  await expect(row.getByRole("link", { name: new RegExp(`^${NAME}\\b`) })).toBeVisible();
  await expect(row.locator(".avatar-row__name", { hasText: NAME })).toBeVisible();
  await expect(chats.getByRole("link", { name: new RegExp(`^${NAME}\\b`) })).toHaveCount(0);
  await openChat(page, NAME);
  await detailPane(page).getByRole("button", { name: `${NAME} menu` }).click();
  await page.getByRole("menuitem", { name: "Unpin" }).click();
  await expect(chats.getByRole("link", { name: new RegExp(`^${NAME}\\b`) })).toBeVisible();
  await expect(row.getByRole("link", { name: new RegExp(`^${NAME}\\b`) })).toHaveCount(0);
});

test("the name pill opens the profile beside the chat, each page in the address, and Back closes it", async ({ page }) => {
  await signIn(page);
  await openChat(page, NAME);
  const composer = detailPane(page).getByPlaceholder(`Message ${NAME}`);
  await detailPane(page).getByRole("link", { name: `Open ${NAME}'s profile` }).click();
  await expect(page).toHaveURL(/[?&]panel=profile\b/);
  const panel = page.getByRole("complementary", { name: `${NAME}'s profile` });
  await openProfilePage(panel, "Settings");
  await expect(page).toHaveURL(/[?&]panel=settings\b/);
  await expect(panel.getByRole("button", { name: /^What I remember/ })).toBeVisible();
  await expect(composer).toBeVisible();
  await openProfilePage(panel, "Computer");
  await expect(page).toHaveURL(/[?&]panel=computer\b/);
  for (let i = 0; i < 4 && new URL(page.url()).searchParams.has("panel"); i += 1) await page.goBack();
  expect(new URL(page.url()).searchParams.has("panel")).toBe(false);
  await expect(composer).toBeVisible();
  await expect(panel).toHaveCount(0);
});

test("the old profile address opens the panel", async ({ page }) => {
  await signIn(page);
  await openChat(page, NAME);
  const id = /\/bots\/([^/?]+)/.exec(page.url())![1];
  await page.goto(`/bots/${id}/profile?tab=links`);
  await expect(page).toHaveURL(/[?&]panel=library\b/);
  await expect(page.getByRole("complementary", { name: `${NAME}'s profile` })).toBeVisible();
});

test.describe("on a phone", () => {
  test.use({ viewport: { width: 390, height: 844 } });
  test("the profile is a full-screen sheet", async ({ page }) => {
    await signIn(page);
    await openChat(page, NAME);
    await detailPane(page).getByRole("link", { name: `Open ${NAME}'s profile` }).click();
    const sheet = page.getByRole("dialog", { name: `${NAME}'s profile` });
    await expect(sheet).toBeVisible();
    // The sheet slides in, so wait for it to settle on the viewport.
    await expect.poll(async () => {
      const box = await sheet.boundingBox();
      return box && { x: Math.round(box.x), y: Math.round(box.y), width: Math.round(box.width), height: Math.round(box.height) };
    }).toEqual({ x: 0, y: 0, width: 390, height: 844 });
    // The sheet carries its own Close button (the aside's "Close profile" is the desktop one).
    await sheet.getByRole("button", { name: "Close", exact: true }).click();
    await expect(sheet).toHaveCount(0);
  });
});

test("the composer is one round pill with its + inside (Earlier conversations is in the ⋯ menu)", async ({ page }) => {
  await signIn(page);
  await openChat(page, NAME);
  const composer = detailPane(page).locator(".composer");
  const input = composer.getByPlaceholder(`Message ${NAME}`);
  const [outer, inner] = [await composer.boundingBox(), await input.boundingBox()];
  expect(outer && inner).toBeTruthy();
  expect(inner!.x).toBeGreaterThanOrEqual(outer!.x);
  expect(inner!.x + inner!.width).toBeLessThanOrEqual(outer!.x + outer!.width);
  await expect(composer.getByRole("button", { name: "More for this chat" })).toHaveCount(0);
  const plus = composer.locator(".composer__leading").getByRole("button", { name: "Add to the chat" });
  await expect(plus).toBeVisible();
  const box = await plus.boundingBox();
  expect(box!.x).toBeGreaterThanOrEqual(outer!.x);
  await plus.click();
  await expect(page.getByRole("menuitem", { name: "Choose file" })).toBeVisible();
  await page.keyboard.press("Escape");
});
