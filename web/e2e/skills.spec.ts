import { readFile } from "node:fs/promises";
import { expect, test, type Page } from "@playwright/test";
import { createBot, detailPane, openProfilePage, say, signIn } from "./helpers";

// Skills (docs/plans/2026-10-21-roost-skills.md, Task 10), against ROOST_DESK=fake + fixtures/team-script.json
// ("Skiller" proposes "Weekly SEO check"). A bot offers a skill on a card; only Save skill writes it. Then the
// user edits it, switches it off for one bot, shares the bot as a template, and imports the file.
const SLOW = { timeout: 20_000 };
const SKILL = "Weekly SEO check";

const chatsPane = (page: Page) => page.getByRole("complementary", { name: "Chats pane" });

async function openSkills(page: Page, name: string) {
  await detailPane(page).getByRole("link", { name: `Open ${name}'s profile` }).click();
  const panel = page.getByRole("complementary", { name: `${name}'s profile` });
  await openProfilePage(panel, "Settings");
  const head = panel.getByRole("button", { name: /^Skills/ });
  if ((await head.getAttribute("aria-expanded")) !== "true") await head.click();
  return panel;
}

test("a bot offers a skill; Save skill keeps it, then edit, switch off, share and import", async ({ page }) => {
  test.setTimeout(90_000);
  await signIn(page);
  await createBot(page, "Skiller", "Checks how the site ranks");
  const chatUrl = page.url().split("?")[0];
  await say(page, "Skiller", "that went well, keep it as a skill");
  const card = detailPane(page).getByRole("region", { name: "New skill" });
  await expect(card).toContainText(SKILL, SLOW);
  await expect(card).toContainText("Report them in one short list");

  await page.goto("/");
  await expect(chatsPane(page).getByRole("region", { name: "My turn" })
    .getByRole("link", { name: `Skiller · New skill · ${SKILL}` })).toBeVisible(SLOW);

  await page.goto(chatUrl);
  await detailPane(page).getByRole("region", { name: "New skill" }).getByRole("button", { name: "Save skill" }).click();
  await expect(detailPane(page).getByText("Saved", { exact: true })).toBeVisible(SLOW);

  // Edit: the editor saves a new revision.
  const panel = await openSkills(page, "Skiller");
  await panel.getByRole("button", { name: new RegExp(SKILL) }).click();
  const editor = page.getByRole("dialog", { name: SKILL });
  await editor.getByRole("textbox", { name: "Steps" }).fill("1. Open the rankings page\n2. Report the three biggest moves");
  await editor.getByRole("button", { name: "Save skill" }).click();
  await expect(editor).toBeHidden(SLOW);

  // Share as Template carries the skill; importing the file offers it, and a name you have is not added twice.
  await panel.getByRole("button", { name: "Share as Template" }).first().click();
  const [download] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: "Save file" }).click()]);
  const file = JSON.parse(await readFile((await download.path())!, "utf8"));
  expect(file.skills).toEqual([{ name: SKILL, use_when: "the user asks how the site ranks this week",
    steps: "1. Open the rankings page\n2. Report the three biggest moves" }]);

  await page.goto("/bots/new");
  const form = detailPane(page);
  await form.getByLabel("From a file").setInputFiles({ name: "Skiller.roost-bot.json", mimeType: "application/json",
    buffer: Buffer.from(JSON.stringify(file)) });
  await expect(form.getByText("This file has 1 skill")).toBeVisible(SLOW);
  await form.getByLabel("Name").fill("Skiller Two");
  await form.getByRole("button", { name: "Create bot" }).click();
  const sheet = page.getByRole("dialog", { name: "Add its skills?" });
  await expect(sheet.getByText("You already have this one")).toBeVisible(SLOW);
  await sheet.getByRole("button", { name: "Skip" }).click();
  await expect(detailPane(page).getByRole("heading", { name: "Skiller Two", exact: true })).toBeVisible(SLOW);

  // Switch it off for Skiller only: Skiller Two keeps it on.
  await page.goto(chatUrl);
  const again = await openSkills(page, "Skiller");
  const toggle = again.getByRole("switch", { name: `On for this bot: ${SKILL}` });
  await toggle.click();
  await expect(toggle).toHaveAttribute("aria-checked", "false", SLOW);
  await expect(again.getByRole("button", { name: /^Skills/ })).toContainText("0 on", SLOW);

  // Clean up, so other specs that share Scout's account see no skills.
  await again.getByRole("button", { name: new RegExp(SKILL) }).click();
  const last = page.getByRole("dialog", { name: SKILL });
  await last.getByRole("button", { name: "Delete" }).click();
  await last.getByRole("button", { name: "Yes, delete it" }).click();
  await expect(again.getByText(/No skills yet/)).toBeVisible(SLOW);
});
