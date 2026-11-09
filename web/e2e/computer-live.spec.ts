import { expect, test } from "@playwright/test";
import { createBot, detailPane, openProfilePage, say, signIn } from "./helpers";

// Computers 2.0 (C1/C2) against ROOST_DESK=fake: the fake desk serves a tiny RFB screen (roost/desk/fake_screen.py)
// and "Courier" (fixtures/team-script.json) opens https://login.example/, a sign-in wall, so the fake computer has a
// page whose host the Vault can label.
const HOST = "login.example";
const SLOW = { timeout: 20_000 };

test("the live screen, the Linux | Mac Brave switch, full-screen Take control, I'm done with an account and the Vault", async ({ page }) => {
  test.setTimeout(120_000);
  await signIn(page);
  await createBot(page, "Courier", "Checks my orders on shop sites");
  const detail = detailPane(page);
  const panel = page.getByRole("complementary", { name: "Courier's profile" });
  await detail.getByRole("link", { name: "Open Courier's profile" }).click();

  // The switch (in Settings): Linux is the usual choice, Mac Brave the optional one; the line under it changes.
  await openProfilePage(panel, "Settings");
  const kind = panel.getByRole("group", { name: "Computer" });
  await kind.getByRole("button", { name: "Linux computer" }).click();
  await expect(panel.getByText(/The usual choice: a sealed Linux computer/)).toBeVisible();
  await kind.getByRole("button", { name: "Mac Brave (optional)" }).click();
  await expect(panel.getByText("Optional: its own Brave window on your Mac.")).toBeVisible();
  await kind.getByRole("button", { name: "Linux computer" }).click();
  await expect(panel.getByText(/The usual choice: a sealed Linux computer/)).toBeVisible();

  // The bot opens a page (a sign-in wall) and waits on a Sign-in card: its computer is awake and has a host.
  await say(page, "Courier", `check my orders on https://${HOST}/`);
  await expect(detail.getByRole("group", { name: `Sign in on ${HOST}` })).toBeVisible(SLOW);

  // The live canvas shows (the fake screen's first frame arrives).
  await openProfilePage(panel, "Computer");
  await panel.getByRole("button", { name: "Open it" }).click();
  const live = panel.getByLabel("Courier’s screen, live");
  await expect(live).toBeVisible(SLOW);
  await expect(live.locator("canvas")).toBeVisible(SLOW);
  const box = await live.locator("canvas").boundingBox();
  expect(box?.width ?? 0).toBeGreaterThan(0);
  expect(box?.height ?? 0).toBeGreaterThan(0);

  // Take control: the screen fills the window; type into it, then I'm done with the account.
  await panel.getByRole("button", { name: "Take control" }).click();
  const control = page.getByRole("dialog");
  await expect(control.getByText("You're in control")).toBeVisible(SLOW);
  const stage = control.getByLabel("Courier’s screen, live");
  await expect(stage.locator("canvas")).toBeVisible(SLOW);
  await stage.locator("canvas").click();
  await page.keyboard.type("secret-pass");
  await control.getByRole("button", { name: "I'm done" }).click();
  await control.getByLabel(/Which account did you use\?/).fill("work email");
  // The Sign-in card is open, so I'm done also asks "Keep me signed in on this computer?".
  await control.getByRole("button", { name: "Yes, keep me signed in" }).click();
  await expect(control).toBeHidden(SLOW);

  // The Vault lists it, the chat says it, and Forget removes it.
  const row = panel.getByText(`${HOST} · work email`);
  await expect(row).toBeVisible(SLOW);
  await expect(detail.getByText(`I signed in on ${HOST} as work email.`)).toBeVisible(SLOW);
  await panel.getByRole("button", { name: `Forget ${HOST} · work email` }).click();
  await expect(panel.getByText("No sign-ins saved yet.")).toBeVisible(SLOW);
});
