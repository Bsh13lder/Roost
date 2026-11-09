import { expect, type Locator, type Page } from "@playwright/test";

const USERNAME = "night1";
const PASSWORD = "a-long-enough-password";

// The gateway allows one account: the first spec to run creates it, every
// later one logs in with it.
// New bots start in "Ask every time". Specs that expect a write to go straight through put the bot in
// Auto-edit through the same route the Info tab uses.
async function setAutoEdit(page: Page, botId: string): Promise<void> {
  const origin = new URL(page.url()).origin;
  const response = await page.request.fetch(`/api/bots/${botId}/approval`, {
    method: "PUT", data: { mode: "auto_edit", ask_topics: [] }, headers: { Origin: origin },
  });
  expect(response.ok(), `auto-edit: ${await response.text()}`).toBe(true);
}

async function mainBotToAutoEdit(page: Page): Promise<void> {
  const bots = (await (await page.request.get("/api/bots")).json()) as { id: string; is_primary: boolean }[];
  const main = bots.find((bot) => bot.is_primary);
  if (main) await setAutoEdit(page, main.id);
}

export async function signIn(page: Page): Promise<void> {
  await signInOnly(page);
  await mainBotToAutoEdit(page);
}

async function signInOnly(page: Page): Promise<void> {
  await page.goto("/login");
  await page.getByText("First time? Create your account").click();
  await page.getByLabel("Username").fill(USERNAME);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();
  const created = await page.waitForURL("/", { timeout: 3_000 }).then(() => true, () => false);
  if (created) return;
  await page.getByText("Already have an account? Log in").click();
  await page.getByLabel("Username").fill(USERNAME);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Log in" }).click();
  await page.waitForURL("/");
}

// On a desktop viewport Home's chat list stays on screen on every route (Task 6's Layout),
// and each row shows a preview of its bot's latest message. Text and name matching is a
// case-insensitive substring match and assertions are strict, so a page-wide query for a
// reply, a document title or a list item also hits that row. Scope content to the detail pane.
export const detailPane = (page: Page): Locator => page.getByRole("main");

export async function createBot(page: Page, name: string, job: string): Promise<void> {
  await page.goto("/");
  await page.getByRole("button", { name: "New", exact: true }).click();
  await page.getByRole("menuitem", { name: "New bot" }).click();
  await page.getByLabel("Name").fill(name);
  await page.getByLabel("Job").fill(job);
  await page.getByRole("button", { name: "Create bot" }).click();
  await page.waitForURL(/\/bots\/[^/?]+$/);
  await expect(detailPane(page).getByRole("heading", { name, exact: true })).toBeVisible();
  const id = new URL(page.url()).pathname.split("/").pop();
  if (id) await setAutoEdit(page, id);
}

export async function openChat(page: Page, name: string): Promise<void> {
  await page.goto("/");
  // A pinned bot (the main bot always) sits in the robot row; every other chat is in the list.
  const lists = page.locator("nav[aria-label='Chats'], ul[aria-label='Your bots']");
  await lists.getByRole("link", { name: new RegExp(`^${name}\\b`) }).click();
  await expect(detailPane(page).getByRole("heading", { name, exact: true })).toBeVisible();
}

export async function say(page: Page, botName: string, text: string): Promise<void> {
  const box = detailPane(page).getByPlaceholder(`Message ${botName}`);
  await box.fill(text);
  await box.press("Enter");
}

// The Workspace's Tasks open on Today (what is late and due today); a task due later is under Upcoming, one with no
// project in the Inbox. Someday, Overdue and Done sit behind More. Each tab carries its count in its name, so match
// the start.
const MORE_VIEWS = new Set(["Overdue", "Someday", "Done"]);
export async function openTaskView(page: Page, view: "Today" | "Inbox" | "Upcoming" | "Overdue" | "Someday" | "Done"): Promise<void> {
  const views = detailPane(page).getByRole("group", { name: "Task views" });
  if (MORE_VIEWS.has(view)) {
    await views.getByRole("button", { name: "More views" }).click();
    await page.getByRole("menuitem", { name: view, exact: true }).click();
    await expect(views.getByRole("button", { name: "More views" })).toHaveText(view);
    return;
  }
  const button = views.getByRole("button", { name: new RegExp(`^${view}\\b`) });
  await button.click();
  await expect(button).toHaveAttribute("aria-pressed", "true");
}

// The Workspace's "Add or find anything…" pill: it filters as you type, and Enter adds the line as a task.
export function workspacePill(page: Page): Locator {
  return detailPane(page).getByRole("combobox", { name: "Add or find anything" });
}

// Tasks · Notes · Calendar.
export async function openSection(page: Page, section: "Tasks" | "Notes" | "Calendar"): Promise<void> {
  const button = detailPane(page).getByRole("group", { name: "Workspace sections" }).getByRole("button", { name: section });
  await button.click();
  await expect(button).toHaveAttribute("aria-pressed", "true");
}

// New project lives in the project chips' menu, beside All money.
export async function startNewProject(page: Page): Promise<void> {
  await detailPane(page).getByRole("button", { name: "Projects and money" }).click();
  await page.getByRole("menuitem", { name: "New project" }).click();
}

// The sidebar's "Workspace" link (the Board's new name) opens Tasks · Notes · Calendar.
export async function openBoard(page: Page): Promise<void> {
  await page.goto("/");
  await page.getByRole("link", { name: "Workspace", exact: true }).click();
  await expect(detailPane(page).getByRole("heading", { name: "Workspace", exact: true })).toBeVisible();
}

// The open chat's bot id, from the address (/bots/:id).
export function botIdFromUrl(page: Page): string {
  return new URL(page.url()).pathname.split("/").filter(Boolean)[1] ?? "";
}

// A JSON call to the gateway with the Origin header every button route asks for.
export async function api(page: Page, method: string, path: string, data?: unknown): Promise<unknown> {
  const origin = new URL(page.url()).origin;
  const response = await page.request.fetch(path, { method, data, headers: { Origin: origin } });
  expect(response.ok(), `${method} ${path}: ${await response.text()}`).toBe(true);
  return response.json();
}

// C3: the bot works on its own Linux computer (opt-in), and that computer is awake.
export async function useLinuxComputer(page: Page, botId: string): Promise<void> {
  await api(page, "PATCH", `/api/bots/${botId}`, { computer: "linux" });
  await api(page, "POST", `/api/bots/${botId}/desk/browser/start`);
}

const escapeRegExp = (text: string) => text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

// The bot's profile is rows (restructure slice 3): Plan & routines, Computer, Library, Settings, each its own page
// with a back arrow. Opens the named page from wherever the panel is; a no-op when it is already shown.
export async function openProfilePage(panel: Page | Locator, label: string): Promise<void> {
  const heading = panel.locator(".profile-page__title").filter({ hasText: new RegExp(`^${escapeRegExp(label)}$`) });
  await expect(panel.locator(".profile-rows, .profile-page__title").first()).toBeVisible(); // the panel's chunk is in
  if (await heading.isVisible()) return;
  const back = panel.getByRole("button", { name: "Back to the profile" });
  if (await back.isVisible()) await back.click();
  await panel.locator(".profile-rows").getByRole("button", { name: new RegExp(`^${escapeRegExp(label)}`) }).click();
  await expect(heading).toBeVisible();
}

// What used to be a fold on the Info tab and is now a page of its own.
const PAGE_OF_FOLD: Readonly<Record<string, string>> = { "Approval mode": "Settings", "Routines and questions": "Plan & routines" };

// The bot's Settings page: each heavier section (What I remember, Decisions, Skills, Question book…) is a fold,
// closed until opened. Opens Settings when the fold is not on screen, then the named fold if it is closed.
export async function openFold(scope: Page | Locator, title: string): Promise<void> {
  if (PAGE_OF_FOLD[title]) return openProfilePage(scope, PAGE_OF_FOLD[title]);
  const escaped = escapeRegExp(title);
  const head = scope.locator("button.fold__head").filter({ hasText: new RegExp(`^${escaped}`) }).first();
  if ((await head.count()) === 0) await openProfilePage(scope, "Settings");
  await expect(head).toBeVisible();
  if ((await head.getAttribute("aria-expanded")) !== "true") await head.click();
  await expect(head).toHaveAttribute("aria-expanded", "true");
}
