import { expect, test } from "@playwright/test";
import { createBot, detailPane, openBoard, openProfilePage, openSection, openTaskView, say, signIn } from "./helpers";

// S1 D2 and the user's own complaint: a brand-new bot with no setup uses tasks, money and documents together.
test("a brand-new bot adds a task, logs an expense and saves the tasks in a document", async ({ page }) => {
  await signIn(page);
  await createBot(page, "Helper", "Helps with anything");
  const detail = detailPane(page);
  await say(page, "Helper", "add call the dentist tomorrow at 9 and log 12.50 for lunch");
  await expect(detail.getByText("Done: the dentist tomorrow at 09:00, and 12.50 EUR for lunch.")).toBeVisible();
  await say(page, "Helper", "save all my tasks in a document");
  // Page-wide, this would also match Helper's chat-row preview in the list pane.
  await expect(detail.getByText("Saved your tasks in My tasks.")).toBeVisible();

  await openBoard(page);
  await openSection(page, "Tasks");   // the Workspace opens on Tasks already; the click is harmless
  await openTaskView(page, "Upcoming");   // tomorrow's task is not in Today
  await expect(detail.getByRole("row").filter({ hasText: "Call the dentist" })).toContainText("by Helper");
  await openSection(page, "Notes");   // one tree of notes and documents; a folder per project, then No project
  await detail.getByRole("button", { name: /^No project/ }).click();
  await expect(detail.getByRole("button", { name: "Doc: My tasks", exact: true })).toBeVisible();

  await page.goto("/");
  await page.getByRole("navigation", { name: "Chats" }).getByRole("link", { name: /^Helper\b/ }).click();
  await detail.getByRole("link", { name: "Open Helper's profile" }).click();
  const panel = page.getByRole("complementary", { name: "Helper's profile" });
  await openProfilePage(panel, "Library");
  await expect(panel.getByRole("region", { name: "Today" })).toBeVisible();
  // In the panel: Helper's chat-row link carries "Saved your tasks in My tasks." in its name.
  await expect(panel.getByRole("link", { name: /^My tasks/ })).toBeVisible();
});
