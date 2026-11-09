import { expect, test } from "@playwright/test";
import { createBot, detailPane, openProfilePage, say, signIn } from "./helpers";

// Stuck flow, design §5 and R11, and its Sign-in card (docs/plans/2026-10-22-roost-signin.md), against
// ROOST_DESK=fake + fixtures/team-script.json ("Porter"). FakeDesk serves https://login.example/ as a sign-in wall
// first and the signed-in page after it (roost/desk/fake_pages.py). On a bot's Linux computer a sign-in wall opens
// a Sign-in card at once: the bot waits for you calmly instead of looking Stuck (the plain Stuck card, on a Mac
// Brave bot, is in chat-feel.spec.ts).
const HOST = "login.example";
const CARD_TITLE = `Sign in on ${HOST}`;
const CARD_LINE = `${HOST}'s sign-in page is open on Porter's computer.`;
const NEVER_SEES_PASSWORD = "Roost never sees your password.";
const WAITING = "Waiting for you to sign in";
const MY_TURN_ROW = `Porter needs you to sign in to ${HOST}`;
const REPLY = "Signed in and done.";
const SLOW = { timeout: 20_000 };

test("a bot meets a sign-in page: the Sign-in card, My turn on Home, then Take control, I'm done and it carries on", async ({ page }) => {
  test.setTimeout(90_000);
  await signIn(page);
  await createBot(page, "Porter", "Checks my orders on shop sites");
  const detail = detailPane(page);
  // The bot works on its own Linux computer (the usual choice): Take control opens its full-screen live screen.
  await detail.getByRole("link", { name: "Open Porter's profile" }).click();
  const panel = page.getByRole("complementary", { name: "Porter's profile" });
  await openProfilePage(panel, "Settings");
  await panel.getByRole("group", { name: "Computer" }).getByRole("button", { name: "Linux computer" }).click();
  await expect(panel.getByText(/The usual choice: a sealed Linux computer/)).toBeVisible();
  const listPane = page.getByRole("complementary", { name: "Chats pane" });
  const porterRow = listPane.getByRole("navigation", { name: "Chats" }).getByRole("link", { name: /^Porter\b/ });
  await say(page, "Porter", "check my orders on https://login.example/");

  // The card names only the host, says what to do and that Roost never sees the password: Take control · Later,
  // with Check again a quiet text button.
  const card = detail.getByRole("group", { name: CARD_TITLE });
  await expect(card).toBeVisible(SLOW);
  await expect(card).toContainText(CARD_LINE);
  await expect(card).toContainText(NEVER_SEES_PASSWORD);
  for (const name of ["Take control", "Later", "Check again"]) {
    await expect(card.getByRole("button", { name, exact: true })).toBeVisible();
  }
  await expect(card.getByRole("button", { name: "Give up", exact: true })).toHaveCount(0);
  // A waiting bot's row shows its calm status line, never its preview.
  await expect(porterRow).toContainText(WAITING, SLOW);

  // Home lives in the Chats pane on every desktop route. After a reload My turn still lists the card
  // (GET /api/stuck), and its row opens the chat.
  await page.goto("/");
  const myTurn = listPane.getByRole("region", { name: "My turn" });
  await expect(myTurn).toBeVisible(SLOW);
  await myTurn.getByRole("link", { name: MY_TURN_ROW }).click();
  await expect(detail.getByRole("heading", { name: "Porter", exact: true })).toBeVisible();

  // Take control opens the sign-in page on the computer, in control, right in the chat under the card (no sheet):
  // the live screen fills the chat column with You're in control · I'm done · Full screen. I'm done with an account
  // and Keep me signed in clears the card (/clear with the account and keep) and the continue run reads the page again.
  await card.getByRole("button", { name: "Take control", exact: true }).click();
  await expect(card.getByText("You're in control")).toBeVisible(SLOW);
  // The fake computer sleeps between runs: the inline screen wakes it once and shows its canvas.
  await expect(card.getByLabel("Porter’s screen, live").locator("canvas")).toBeVisible(SLOW);
  await expect(card.getByRole("button", { name: "Full screen" })).toBeVisible();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await card.getByRole("button", { name: "I'm done" }).click();
  await card.getByLabel(/Which account did you use\?/).fill("work email");
  await expect(card.getByRole("group", { name: "Keep me signed in on this computer?" })).toBeVisible();
  await card.getByRole("button", { name: "Yes, keep me signed in" }).click();
  await expect(detail.getByRole("group", { name: `Cleared: ${HOST}` })).toBeVisible(SLOW);
  await expect(detail.getByText(`I signed in on ${HOST} as work email.`)).toBeVisible(SLOW);
  await expect(detail.getByText(REPLY)).toBeVisible(SLOW);
  // Resting again: the row shows the reply as its preview (a waiting or On it bot shows its status there instead).
  await expect(porterRow).toContainText(REPLY, SLOW);
  await expect(myTurn).toBeHidden(SLOW);
});
