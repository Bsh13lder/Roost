import { expect, test } from "@playwright/test";
import { createBot, detailPane, openChat, say, signIn } from "./helpers";

// The chat (redesign P2), against fixtures/team-script.json's "Writer": a step that adds a task, then a
// markdown reply with a heading, a list, a [[wikilink]], a wide table, a long code line and a link.
// The first spec, alphabetically: it creates the account, and Writer, whom the second test reuses.
test.use({ permissions: ["clipboard-read", "clipboard-write"] });

test("a markdown reply: its step, a heading, a chip, a table and code that scroll inside it, and Copy code", async ({ page }) => {
  await signIn(page);
  await createBot(page, "Writer", "Writes things up");
  const detail = detailPane(page);
  await say(page, "Writer", "plan my week");
  const reply = detail.locator(".message--card");
  await expect(reply.getByRole("heading", { name: "Your week" })).toBeVisible();
  // Its step is in the activity pill's folded line; the sheet says it in words.
  await expect(reply.getByTestId("activity-line")).toContainText("1 step");
  await expect(reply.locator(".wikilink-chip", { hasText: "Garden plan" })).toBeVisible();
  await expect(reply.getByRole("link", { name: "docs.example" })).toHaveAttribute("rel", "noopener noreferrer");

  // Review Focus 4: a wide table and a long code line scroll inside the reply, never the chat or the page.
  for (const wide of [reply.getByRole("region", { name: "Table" }), reply.locator(".md__code pre")]) {
    expect(await wide.evaluate((element) => element.scrollWidth > element.clientWidth)).toBe(true);
  }
  expect(await page.locator(".chat-page__scroll").evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);

  await reply.getByRole("button", { name: "Copy code" }).click();
  await expect(reply.getByRole("button", { name: "Copied" })).toBeVisible();
  expect(await page.evaluate(() => navigator.clipboard.readText())).toContain("const plan = [");
});

test.describe("on a short screen", () => {
  test.use({ viewport: { width: 1280, height: 560 } });

  test("the composer grows with its text, clips no letter and keeps the last message in view", async ({ page }) => {
    await signIn(page);
    await openChat(page, "Writer");
    const detail = detailPane(page);
    const scroller = page.locator(".chat-page__scroll");
    await expect(detail.locator(".message--card")).toBeVisible();
    expect(await scroller.evaluate((element) => element.scrollHeight > element.clientHeight)).toBe(true);

    const box = detail.getByPlaceholder("Message Writer");
    const oneLine = (await box.boundingBox())!.height;
    await box.fill(Array.from({ length: 5 }, (_, line) => `Line ${line + 1} of a longer message`).join("\n"));
    await expect.poll(async () => (await box.boundingBox())!.height).toBeGreaterThan(oneLine * 2.5);
    expect(await box.evaluate((element) => element.scrollHeight <= element.clientHeight + 1)).toBe(true);
    expect(await box.evaluate((element) => getComputedStyle(element).borderTopLeftRadius)).toBe("0px");

    const shown = (await scroller.boundingBox())!;
    await expect.poll(async () => {
      const last = (await detail.locator(".message-list > .message").last().boundingBox())!;
      return last.y + last.height <= shown.y + shown.height + 1;
    }).toBe(true);
  });
});
