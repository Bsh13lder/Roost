import { readFile } from "node:fs/promises";
import { expect, test } from "@playwright/test";
import { detailPane, openChat, openProfilePage, signIn } from "./helpers";

test("change a bot's look and instructions, share it as a template and import it", async ({ page }) => {
  await signIn(page);
  await openChat(page, "Scout");
  await detailPane(page).getByRole("link", { name: "Open Scout's profile" }).click();
  const detail = page.getByRole("complementary", { name: "Scout's profile" });
  await detail.getByRole("button", { name: "Edit", exact: true }).click(); // Edit opens the look, name and job
  await detail.getByRole("button", { name: "Edit look" }).click();
  const card = page.getByRole("dialog", { name: "Edit look" });
  // The radios are visually hidden, so click the label around each one (as a person does). Each pick
  // saves through a round trip (AvatarEditor) before the DOM reflects it, so click then await
  // the checked state as its own assertion rather than locator.check()'s single-shot verify.
  await card.getByRole("radio", { name: "Pebble" }).locator("xpath=..").click();
  await expect(card.getByRole("radio", { name: "Pebble" })).toBeChecked();
  await card.getByRole("radio", { name: "Teal" }).locator("xpath=..").click();
  await expect(card.getByRole("radio", { name: "Teal" })).toBeChecked();
  const roles = card.getByRole("group", { name: "Role" });
  await roles.getByRole("button", { name: "Writer" }).click();
  await expect(roles.getByRole("button", { name: "Writer" })).toHaveAttribute("aria-pressed", "true");
  await page.keyboard.press("Escape");
  await openProfilePage(detail, "Settings");
  await detail.getByRole("link", { name: /Instructions/ }).click();
  // The editor is a full page; Save returns to the chat with the panel open on Settings.
  await detailPane(page).getByRole("textbox", { name: "Instructions" }).fill("Always give opening hours in 24h time.");
  await detailPane(page).getByRole("button", { name: "Save" }).click();
  await expect(detail.getByText("Always give opening hours in 24h time.")).toBeVisible();

  await detail.getByRole("button", { name: "Share as Template" }).first().click();
  const [download] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: "Save file" }).click()]);
  expect(download.suggestedFilename()).toBe("Scout.roost-bot.json");
  const file = JSON.parse(await readFile((await download.path())!, "utf8"));
  expect(Object.keys(file).sort()).toEqual(["avatar", "format", "instructions", "job", "name", "version"]);
  // A Lensbot has no screen; the stored style (the default) still rides along for older readers. The role rides too.
  expect(file.avatar).toEqual({ shape: "pebble", color: "#14b8a6", screen: "glow", role: "writer" });

  await page.goto("/bots/new");
  const form = detailPane(page);
  await form.getByLabel("From a file").setInputFiles({ name: "Scout.roost-bot.json", mimeType: "application/json",
    buffer: Buffer.from(JSON.stringify(file)) });
  await expect(form.getByLabel("Instructions")).toHaveValue("Always give opening hours in 24h time.");
  await form.getByLabel("Name").fill("Scout Two");
  await form.getByRole("button", { name: "Create bot" }).click();
  await expect(form.getByRole("heading", { name: "Scout Two", exact: true })).toBeVisible();
});
