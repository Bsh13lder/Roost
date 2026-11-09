import { expect, test, type Page } from "@playwright/test";
import { createBot, detailPane, openFold, say, signIn } from "./helpers";

// Voice (docs/plans/2026-10-30-roost-voice.md V3), against the gateway's fake voice (ROOST_VOICE=fake: it hears
// every recording as "Add milk to my list" and speaks silence). "Parrot" has no script, so it echoes: this spec
// takes nothing from fixtures/team-script.json.
test.describe.configure({ mode: "serial" });

const NAME = "Parrot";

async function openSettings(page: Page) {
  await detailPane(page).getByRole("link", { name: `Open ${NAME}'s profile` }).click();
  return page.getByRole("complementary", { name: `${NAME}'s profile` });
}

test("a bot's reply has a speaker that reads it aloud", async ({ page }) => {
  await signIn(page);
  await createBot(page, NAME, "Repeats what you say");
  await say(page, NAME, "hello there");
  const reply = detailPane(page).locator("li.message--bot").filter({ hasText: "I heard: hello there" });
  await expect(reply).toHaveCount(1);
  await reply.hover();
  const part = page.waitForResponse((response) => /\/speech\/0$/.test(new URL(response.url()).pathname));
  await reply.getByRole("button", { name: "Read aloud" }).click();
  expect((await part).status()).toBe(200);
});

test("the Voice fold saves the tone, and Try it plays a sample", async ({ page }) => {
  await signIn(page);
  await page.goto("/");
  await page.locator("nav[aria-label='Chats'], ul[aria-label='Your bots']").getByRole("link", { name: new RegExp(`^${NAME}\\b`) }).click();
  const panel = await openSettings(page);
  await openFold(panel, "Voice");
  await expect(panel.getByRole("combobox", { name: "Voice" })).toHaveText(/Aiden/);
  await panel.getByRole("combobox", { name: "Tone" }).click();
  await page.getByRole("option", { name: "Calm" }).click();
  await expect(panel.getByRole("combobox", { name: "Tone" })).toHaveText(/Calm/);

  const sample = page.waitForResponse((response) => response.url().includes("/voice/sample?speaker=aiden&tone=calm"));
  await panel.getByRole("button", { name: "Try it" }).click();
  expect((await sample).status()).toBe(200);

  await page.reload();
  const again = page.getByRole("complementary", { name: `${NAME}'s profile` });
  await openFold(again, "Voice");
  await expect(again.getByRole("combobox", { name: "Tone" })).toHaveText(/Calm/);
});
