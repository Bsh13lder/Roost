import { expect, test, type Page } from "@playwright/test";
import { createBot, detailPane, openFold, say, signIn } from "./helpers";

// Approval modes + Your Mac, against ROOST_DESK=fake with the fake Mac tree (fixtures/mac-tree.json) and the
// "Clerk" script: one mac_write_new, a parked run ends at the card, and the run Yes starts says the last line.
const SLOW = { timeout: 20_000 };
const FILE_LINE = "Created hello.md · MySpace";

async function shareMySpace(page: Page, botId: string): Promise<void> {
  const origin = new URL(page.url()).origin;
  const headers = { Origin: origin };
  const picked = await page.request.fetch("/api/mac/pick-folder", { method: "POST", data: {}, headers });
  const { path } = (await picked.json()) as { path: string | null };
  expect(path, "the fake Mac has a folder to pick").toBeTruthy();
  const granted = await page.request.fetch("/api/mac/grants", {
    method: "POST", headers,
    data: { path, label: "MySpace", access: "read_write", read_policy: "ask_each", bot_id: botId },
  });
  expect(granted.ok(), await granted.text()).toBe(true);
}

test("in Ask every time a write waits on an Ask card; Yes runs it and the activity line has Undo", async ({ page }) => {
  test.setTimeout(90_000);
  await signIn(page);
  await createBot(page, "Clerk", "Keeps my notes folder tidy");
  const detail = detailPane(page);
  const botId = new URL(page.url()).pathname.split("/").pop() ?? "";

  // Info tab: put Clerk back in Ask every time, and share the folder through the same routes the Folders card uses.
  await detail.getByRole("link", { name: /Open Clerk's profile/ }).click();
  await openFold(detail, "Approval mode");
  await openFold(detail, "Folders it may use");
  await detail.getByRole("button", { name: "Ask every time", exact: true }).click();
  await expect(detail.getByRole("button", { name: "Ask every time", exact: true })).toHaveAttribute("aria-pressed", "true");
  await shareMySpace(page, botId);
  await page.reload();
  await expect(detail.getByText("MySpace", { exact: true })).toBeVisible(SLOW);
  await detail.getByRole("link", { name: /Close Clerk's profile/ }).click();

  await say(page, "Clerk", "save hello.md in MySpace");
  const card = detail.getByRole("group", { name: "Needs your OK" });
  await expect(card).toBeVisible(SLOW);
  await expect(card).toContainText("hello.md");
  await expect(card.getByText("+1 −0 lines")).toBeVisible();

  await card.getByRole("button", { name: "Yes", exact: true }).click();
  await expect(detail.locator(".approval-line").filter({ hasText: "You said yes: " })).toBeVisible(SLOW);
  const line = detail.locator(".message--mac").filter({ hasText: FILE_LINE });
  await expect(line).toBeVisible(SLOW);
  await expect(line.getByRole("button", { name: "Undo" })).toBeVisible();
  await expect(detail.getByText("Saved hello.md.")).toBeVisible(SLOW);

  // Undo moves the new file to the trash and says so.
  await line.getByRole("button", { name: "Undo" }).click();
  await expect(detail.getByText(/Undid the creation of hello\.md · MySpace|Moved hello\.md to the trash/).first()).toBeVisible(SLOW);
  await expect(line.getByRole("button", { name: "Undo" })).toBeHidden();
});
