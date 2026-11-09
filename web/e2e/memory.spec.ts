import { expect, test } from "@playwright/test";
import { createBot, detailPane, openFold, openProfilePage, say, signIn } from "./helpers";

// Memory and the one endless chat, against the scripted gateway: its ScriptedWorker captures "Remember that ...".
const FACT = "Ana's birthday is in May and she loves orchids";

test("a remembered fact shows in the chat and on the Profile, and Undo forgets it", async ({ page }) => {
  await signIn(page);
  await createBot(page, "Mia", "Keeps track of things");
  const detail = detailPane(page);
  await say(page, "Mia", `Remember that ${FACT}`);
  await expect(detail.getByText(`Remembered: ${FACT}`)).toBeVisible();

  await detail.getByRole("link", { name: "Open Mia's profile" }).click();
  const panel = page.getByRole("complementary", { name: "Mia's profile" });
  await openFold(panel, "What I remember");
  const memory = panel.getByRole("region", { name: "What I remember" });
  await expect(memory.getByRole("group", { name: "About you" })).toContainText(FACT);

  await panel.getByRole("button", { name: "Close profile" }).click();
  await detail.getByRole("button", { name: /^Undo/ }).click();
  await expect(detail.getByText(`Forgot: ${FACT}`)).toBeVisible();

  await detail.getByRole("link", { name: "Open Mia's profile" }).click();
  await openProfilePage(panel, "Settings");
  await expect(memory.getByRole("group", { name: "About you" })).toContainText("Nothing yet.");
});

test("the chat has no New conversation and earlier conversations are read-only", async ({ page }) => {
  await signIn(page);
  await page.goto("/");
  await page.getByRole("navigation", { name: "Chats" }).getByRole("link", { name: /^Mia\b/ }).click();
  const detail = detailPane(page);
  await detail.getByRole("button", { name: "Mia menu" }).click();
  await expect(page.getByRole("menuitem", { name: "Earlier conversations" })).toBeVisible();
  await expect(page.getByRole("menuitem", { name: /New conversation/i })).toHaveCount(0);
});
