import { expect, test, type Locator, type Page } from "@playwright/test";
import { detailPane, openChat, say, signIn } from "./helpers";

const LENSBOTS = ["mochi", "loaf", "gumdrop", "pebble", "bun", "acorn", "marsh", "dumpling", "muffs", "squish", "cub", "sprout",
  "cheeky", "tower", "helmet", "bell", "puck", "pod"];

// The avatar editor (redesign P1, Lensbots since avatars v7): Surprise me, a drag across the shape tiles,
// a role from the Role row, and Scout's own picture inside its robot. computer.spec (earlier, alphabetically) made Scout;
// profile.spec (later) picks its own shape and colour, so nothing here leaks into it.
const PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==", "base64");
const PICTURE_URL = /^\/api\/bots\/[^/]+\/picture\?v=[0-9a-f]{12}$/;

// The look card under the hero robot: the eighteen shapes are real tiles (not slivers), clickable, and
// nothing in the card spills sideways or out of the window.
async function expectShapeTilesFit(card: Locator, page: Page): Promise<void> {
  const tiles = card.locator(".avatar-picker__shape");
  await expect(tiles).toHaveCount(18);
  for (let i = 0; i < 18; i += 1) {
    const box = await tiles.nth(i).boundingBox();
    expect(box?.width ?? 0).toBeGreaterThanOrEqual(40);
    expect(box?.height ?? 0).toBeGreaterThanOrEqual(40);
  }
  const spill = await card.evaluate((el, viewport) => {
    const edge = el.getBoundingClientRect();
    const wide = [...el.querySelectorAll("*")].filter((c) => {
      const r = c.getBoundingClientRect();
      return r.width > 0 && (r.right > edge.right + 1 || r.left < edge.left - 1);
    });
    return { scrolls: el.scrollWidth > el.clientWidth, outside: edge.right > viewport || edge.left < 0, wide: wide.map((c) => c.className.toString()) };
  }, page.viewportSize()?.width ?? 0);
  expect(spill).toEqual({ scrolls: false, outside: false, wide: [] });
  await tiles.nth(1).click();
  await expect(tiles.nth(1).getByRole("radio")).toBeChecked();
}

test("the avatar editor: Surprise me, a drag across the shapes, a role, and Scout's own picture inside its robot", async ({ page }) => {
  await signIn(page);
  await openChat(page, "Scout");
  await detailPane(page).getByRole("link", { name: "Open Scout's profile" }).click();
  const detail = page.getByRole("complementary", { name: "Scout's profile" });
  await detail.getByRole("button", { name: "Edit", exact: true }).click(); // Edit opens the look, name and job
  const hero = detail.getByRole("button", { name: "Edit look" });
  const robot = hero.locator("svg.avatar");
  await expect(robot).toHaveAttribute("data-moment", "rest"); // the hero shows Scout's own status
  // A Lensbot: a shape, a dark visor, two open white eyes, no screen, and no emblem until it has a role.
  await expect(robot).toHaveAttribute("data-shape", new RegExp(`^(${LENSBOTS.join("|")})$`));
  await expect(robot.locator(".robot__visor").first()).toBeVisible();
  await expect(robot.locator(".robot__emblem")).toHaveCount(0);
  await expect(robot).toHaveAttribute("data-face", "open");
  await expect(robot.locator(".robot__eye .robot__lens")).toHaveCount(2);
  await expect(robot).toHaveClass(/robot--live/);
  await expect(page.getByRole("dialog", { name: "Edit look" })).toHaveCount(0);
  await hero.click();
  const card = page.getByRole("dialog", { name: "Edit look" });
  await expectShapeTilesFit(card, page);

  const before = await robot.getAttribute("data-shape");
  const surprised = page.waitForResponse((r) => /\/api\/bots\/[^/]+$/.test(r.url()) && r.request().method() === "PATCH");
  await card.getByRole("button", { name: "Surprise me" }).click();
  expect((await surprised).ok()).toBe(true);
  await expect(robot).not.toHaveAttribute("data-shape", before ?? "");

  // Press on Mochi and drag to Bell: the hero morphs along the way and the release saves Bell.
  const tile = (name: string) => card.getByRole("radio", { name }).locator("xpath=..");
  const from = (await tile("Mochi").boundingBox())!;
  const to = (await tile("Bell").boundingBox())!;
  const dragged = page.waitForResponse((r) => /\/api\/bots\/[^/]+$/.test(r.url()) && r.request().method() === "PATCH");
  await page.mouse.move(from.x + from.width / 2, from.y + from.height / 2);
  await page.mouse.down();
  await page.mouse.move(to.x + to.width / 2, to.y + to.height / 2, { steps: 8 });
  await expect(robot).toHaveAttribute("data-shape", "bell");
  await page.mouse.up();
  expect((await dragged).ok()).toBe(true);
  await expect(tile("Bell").getByRole("radio")).toBeChecked();
  await expect(card.getByRole("radio", { name: /icons|Signals/ })).toHaveCount(0); // no screen row

  // The Role row: Scout's job names no role, so nothing is suggested; one click saves Research, and its
  // emblem shows on the hero and on Scout's row in the chat list.
  const roles = card.getByRole("group", { name: "Role" });
  await expect(roles.getByRole("button")).toHaveCount(8);
  await expect(card.getByText(/Suggested from its job/)).toHaveCount(0);
  const roled = page.waitForResponse((r) => /\/api\/bots\/[^/]+$/.test(r.url()) && r.request().method() === "PATCH");
  await roles.getByRole("button", { name: "Research" }).click();
  const saved = await roled;
  expect(saved.request().postDataJSON().avatar.role).toBe("research");
  expect((await saved.json()).avatar.role).toBe("research");
  await expect(roles.getByRole("button", { name: "Research" })).toHaveAttribute("aria-pressed", "true");
  await expect(robot).toHaveAttribute("data-role", "research");
  await expect(robot.locator(".robot__emblem--research")).toHaveCount(1);
  const row = page.getByRole("navigation", { name: "Chats" }).getByRole("link", { name: /^Scout\b/ });
  await expect(row.locator("svg.robot .robot__emblem--research")).toHaveCount(1);

  // From the keyboard, the Upload a picture button (a label over a hidden file input) shows a focus ring.
  await card.getByRole("tab", { name: "Upload" }).click();
  const upload = card.getByLabel("Upload a picture");
  await upload.focus();
  await page.keyboard.press("Shift+Tab");
  await page.keyboard.press("Tab");
  await expect(card.locator(".avatar-studio__upload")).toHaveCSS("outline-style", "solid");

  const uploaded = page.waitForResponse((r) => r.url().endsWith("/picture") && r.request().method() === "POST");
  await upload.setInputFiles({ name: "scout.png", mimeType: "image/png", buffer: PNG });
  expect((await uploaded).status()).toBe(200);
  const picture = robot.locator("image.robot__picture");
  await expect(picture).toHaveAttribute("href", PICTURE_URL);
  // The picture fills the body, inside its clip; the eyes stay off it, and the status is its posture.
  await expect(picture).toHaveAttribute("clip-path", /^url\(#robot-clip-/);
  await expect(robot.locator(".robot__eye")).toHaveCount(0);
  await expect(robot).toHaveAttribute("data-moment", "rest");
  const served = await page.request.get((await picture.getAttribute("href"))!);
  expect(served.status()).toBe(200);
  expect(served.headers()["content-type"]).toMatch(/^image\/(webp|png)$/); // shrunk in the browser first

  await card.getByRole("button", { name: "Remove picture" }).click();
  await expect(robot.locator("image.robot__picture")).toHaveCount(0);
  await expect(robot.locator(".robot__eye")).toHaveCount(2);
});

// The chat takes the bot's colour: a blue bot's own bubble is blue, and it follows the colour picked in the card.
test("the chat takes the bot's colour, and follows a change made in the look card", async ({ page }) => {
  await signIn(page);
  await openChat(page, "Scout");
  await say(page, "Scout", "hello there");
  const bubble = detailPane(page).locator(".message--user .message__body").last();
  await expect(bubble).toBeVisible();
  const open = detailPane(page).getByRole("link", { name: "Open Scout's profile" });
  await open.click();
  const detail = page.getByRole("complementary", { name: "Scout's profile" });
  await detail.getByRole("button", { name: "Edit", exact: true }).click(); // Edit opens the look, name and job
  await detail.getByRole("button", { name: "Edit look" }).click();
  const card = page.getByRole("dialog", { name: "Edit look" });
  await card.getByRole("radio", { name: "Blue" }).locator("xpath=..").click();
  await expect(card.getByRole("radio", { name: "Blue" })).toBeChecked();
  await expect(bubble).toHaveCSS("background-color", "rgb(59, 130, 246)");
  await card.getByRole("radio", { name: "Orange" }).locator("xpath=..").click();
  await expect(bubble).toHaveCSS("background-color", "rgb(249, 115, 22)");
  // The panel and the sidebar keep the app accent.
  await expect(detail.getByRole("button", { name: "Done", exact: true })).not.toHaveCSS("color", "rgb(249, 115, 22)");
});
