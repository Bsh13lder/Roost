import { expect, test, type Page } from "@playwright/test";
import { createBot, detailPane, openBoard, openSection, openTaskView, say, signIn, workspacePill } from "./helpers";

// "Expenses, tasks, notes, documents management, PDF, sheets — everything stays": a plain new bot does
// all of it (S1 D2, no roles). ROOST_MODEL=scripted + fixtures/team-script.json ("Office", "Life admin").
test.describe.configure({ mode: "serial" });

async function sayAndSee(page: Page, bot: string, text: string, reply: string): Promise<void> {
  await say(page, bot, text);
  await expect(detailPane(page).getByText(reply)).toBeVisible();
}

// What read_document shows for a document, through the same session.
async function documentText(page: Page, title: string): Promise<string> {
  const listed = (await (await page.request.get("/api/documents")).json()) as { id: string; title: string }[];
  const found = listed.filter((doc) => doc.title === title);
  expect(found, `exactly one document titled ${title}`).toHaveLength(1);
  const body = (await (await page.request.get(`/api/documents/${found[0].id}/text`)).json()) as { text: string };
  return body.text;
}

test("a new bot saves tasks in a doc, October expenses in a sheet, and a note it finds again", async ({ page }) => {
  const problems: string[] = [];
  page.on("pageerror", (error) => problems.push(`pageerror: ${error.message}`));
  page.on("console", (message) => { if (message.type() === "error") problems.push(`console: ${message.text()}`); });
  await signIn(page);
  await createBot(page, "Office", "Keeps my records");
  await sayAndSee(page, "Office", "remind me to buy orchids for Ana", "Added: Buy orchids for Ana.");
  await sayAndSee(page, "Office", "save all my tasks in a document", "Saved your tasks in “Task list”.");
  await sayAndSee(page, "Office", "spent 12.50 on lunch on 3 October, food", "Logged 12.50 EUR to food on 3 October.");
  await sayAndSee(page, "Office", "make a sheet of my October expenses", "Made the sheet “October expenses”.");
  await say(page, "Office", "note: Ana's birthday is 3 May, she likes orchids");
  // Redesign P2: the reply is markdown, so its [[Ana]] is a chip.
  const saved = detailPane(page).locator(".message--bot").filter({ hasText: "Saved to" });
  await expect(saved.locator(".wikilink-chip", { hasText: "Ana" })).toBeVisible();

  const detail = detailPane(page);
  await openBoard(page);
  // The Workspace's Notes: one tree of notes and documents; these belong to no project.
  await openSection(page, "Notes");
  await detail.getByRole("button", { name: /^No project/ }).click();
  const documents = detail.getByRole("group", { name: "No project" });
  await expect(documents.getByRole("button", { name: "Doc: Task list", exact: true })).toBeVisible();
  await expect(documents.getByRole("button", { name: "Sheet: October expenses", exact: true })).toBeVisible();
  expect(await documentText(page, "Task list")).toContain("Buy orchids for Ana");
  expect(await documentText(page, "October expenses")).toContain("lunch");

  // Redesign P1 Task 2 deduped the Radix packages under Univer: both editors must still mount, clean.
  const before = problems.length;
  for (const title of ["Doc: Task list", "Sheet: October expenses"]) {
    await documents.getByRole("button", { name: title, exact: true }).click();
    await expect(detail.getByTestId("univer-editor").locator("canvas").first()).toBeVisible();   // Univer really mounted
    await expect(detail.getByText("Not saved")).toHaveCount(0);
    await detail.getByRole("button", { name: "← Documents" }).click();
  }
  expect(problems.slice(before), "no page error or console error while the editors opened").toEqual([]);

  // The pill filters the tree by title as you type; the note opens in the note editor.
  await workspacePill(page).fill("Ana");
  await detail.getByRole("button", { name: "Note: Ana", exact: true }).click();
  await expect(detail.getByRole("textbox", { name: "Note text" })).toHaveValue(/orchids/);
});

test("a new bot keeps the user's tasks and money in the shared Workspace", async ({ page }) => {
  await signIn(page);
  await createBot(page, "Life admin", "Keeps my appointments and spending");
  await sayAndSee(page, "Life admin", "remind me tomorrow at 9 to call the dentist", "Done. Call the dentist, tomorrow at 09:00.");
  await sayAndSee(page, "Life admin", "spent 12.50 on lunch, food", "Logged 12.50 EUR to food.");

  const detail = detailPane(page);
  await openBoard(page);
  // The Workspace opens on Tasks; projects are its chips, Money sits under All money.
  await expect(detail.getByRole("group", { name: "Workspace sections" }).getByRole("button", { name: "Tasks" }))
    .toHaveAttribute("aria-pressed", "true");
  // The Board is shared: Helper (every-bot.spec) has a "Call the dentist" too. Pick Life admin's row.
  await openTaskView(page, "Upcoming");   // the Tasks tab opens on Today; tomorrow's task is under Upcoming
  const task = detail.getByRole("row").filter({ hasText: "Call the dentist" }).filter({ hasText: "by Life admin" });
  await expect(task).toContainText(/Tomorrow/); // the due column says the day; the time and the reminder live in the drawer

  await detail.getByRole("button", { name: "Projects and money" }).click();
  await page.getByRole("menuitem", { name: "All money" }).click();
  // The "By project" table sums every bot's food, so check Life admin's own expense row.
  const expense = detail.getByRole("list", { name: "Expenses" }).getByRole("listitem").filter({ hasText: "by Life admin" });
  await expect(expense).toContainText("food");
  await expect(expense).toContainText("12.50");
});
