// README screenshots and a short demo video of Roost, made with fake demo data (a small café, "Café Lumen") on a
// throwaway scripted gateway. Never calls a real model (ROOST_MODEL=scripted with web/e2e/fixtures/readme-script.json),
// never touches the live gateway (18800), the keeper (18801), Brave, port 9222 or Docker (ROOST_DESK=fake).
//
// Run from the repo root (needs web/node_modules; builds web/dist when it is missing or older than web/src):
//   node scripts/readme-shots.mjs
//
// Writes docs/screenshots/*.png and docs/screenshots/demo.webm.
import { spawn, execFileSync } from "node:child_process";
import { createRequire } from "node:module";
import { existsSync, mkdirSync, mkdtempSync, openSync, readdirSync, renameSync, rmSync, statSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { BOTS, EXPENSES, MESSAGES, PROJECTS, ROUTINES, TASKS } from "./readme-shots-data.mjs";

const REPO = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const WEB = join(REPO, "web");
const OUT = join(REPO, "docs", "screenshots");
const PORT = 5173;                       // an allowed origin in roost/config.py, never 18800
const BASE = `http://127.0.0.1:${PORT}`;
const MIN_FREE_GB = 8;
const DESKTOP = { width: 1440, height: 900 };
const PHONE = { width: 390, height: 844 };
const VIDEO_SIZE = { width: 1280, height: 800 };
const SLOW = { timeout: 60_000 };
const USERNAME = "demo";
const PASSWORD = "a-long-enough-password";

// --- safety and setup ------------------------------------------------------------------------------------------

function freeGb() {
  const line = execFileSync("df", ["-g", "/System/Volumes/Data"], { encoding: "utf8" }).split("\n")[1];
  return Number(line.trim().split(/\s+/)[3]);
}

function diskGuard(step) {
  const free = freeGb();
  if (!(free >= MIN_FREE_GB)) throw new Error(`${step}: only ${free} GB free, need ${MIN_FREE_GB}`);
}

function newestMtime(dir) {
  let newest = 0;
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name);
    newest = Math.max(newest, entry.isDirectory() ? newestMtime(path) : statSync(path).mtimeMs);
  }
  return newest;
}

function ensureWebBuilt() {
  if (!existsSync(join(WEB, "node_modules"))) {
    diskGuard("npm install");
    execFileSync("npm", ["install"], { cwd: WEB, stdio: "inherit" });
  }
  const index = join(WEB, "dist", "index.html");
  if (existsSync(index) && statSync(index).mtimeMs >= newestMtime(join(WEB, "src"))) return;
  console.log("building web/dist…");
  execFileSync("npm", ["run", "build"], { cwd: WEB, stdio: "inherit" });
}

async function portBusy() {
  try { await fetch(`${BASE}/api/auth/me`, { signal: AbortSignal.timeout(1500) }); return true; } catch { return false; }
}

function startGateway() {
  const env = {
    ...process.env,
    ROOST_MODEL: "scripted",
    ROOST_MODEL_SCRIPT: "web/e2e/fixtures/readme-script.json",
    ROOST_SCHEDULER_TICK_SECONDS: "2",
    ROOST_STEER_DEBOUNCE_SECONDS: "0",
    ROOST_DESK: "fake",
    ROOST_VOICE: "fake",
    ROOST_FAKE_SCREEN: "shop",
    ROOST_FAKE_MAC_TREE: "web/e2e/fixtures/mac-tree.json",
    ROOST_MAC_HOME: mkdtempSync(join(tmpdir(), "roost-readme-mac-")),
    ROOST_DATA_DIR: mkdtempSync(join(tmpdir(), "roost-readme-data-")),
    ROOST_DESKS_DIR: mkdtempSync(join(tmpdir(), "roost-readme-desks-")),
  };
  delete env.ANTHROPIC_API_KEY;
  const args = ["run", "uvicorn", "roost.gateway.app:create_app", "--factory", "--host", "127.0.0.1", "--port", String(PORT)];
  const log = join(mkdtempSync(join(tmpdir(), "roost-readme-log-")), "gateway.log");
  console.log(`gateway log: ${log}`);
  const out = openSync(log, "a");
  return spawn("uv", args, { cwd: REPO, env, stdio: ["ignore", out, out], detached: true });
}

async function waitUp() {
  for (let i = 0; i < 120; i += 1) {
    try { const r = await fetch(`${BASE}/api/auth/me`); if (r.status < 500) return; } catch { /* not yet */ }
    await new Promise((ok) => setTimeout(ok, 500));
  }
  throw new Error("the scripted gateway did not start");
}

// --- the app ---------------------------------------------------------------------------------------------------

async function signUp(page) {
  await page.goto("/login");
  await page.getByText("First time? Create your account").click();
  await page.getByLabel("Username").fill(USERNAME);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();
  await page.waitForURL(`${BASE}/`);
}

// Same-origin fetch from the page, so the session cookie and the Origin header ride along.
const api = (page, method, path, body) => page.evaluate(async ([m, p, b]) => {
  const r = await fetch(p, { method: m, headers: { "Content-Type": "application/json" }, body: b ? JSON.stringify(b) : undefined });
  const text = await r.text();
  if (!r.ok) throw new Error(`${m} ${p} ${r.status} ${text}`);
  return text ? JSON.parse(text) : null;
}, [method, path, body]);

const day = (offset) => { const d = new Date(); d.setDate(d.getDate() + offset); return d.toISOString().slice(0, 10); };

async function seedBots(page) {
  const bots = {};
  for (const bot of await api(page, "GET", "/api/bots")) bots[bot.is_primary ? "Chief" : bot.name] = bot.id;
  for (const { name, job, shape, color, role } of BOTS) {
    const made = await api(page, "POST", "/api/bots", { name, job, instructions: "", avatar: { shape, color, role } });
    bots[name] = made.id;
  }
  for (const [name, id] of Object.entries(bots)) {
    const mode = name === "Shop helper" ? "ask" : "auto_edit";   // Ask every time: the buy click shows its card
    await api(page, "PUT", `/api/bots/${id}/approval`, { mode, ask_topics: [] });
  }
  await api(page, "PATCH", `/api/bots/${bots["Shop helper"]}`, { computer: "linux" });
  await api(page, "POST", `/api/bots/${bots["Shop helper"]}/desk/browser/start`);
  return bots;
}

async function seedSteps(page, taskId, steps, doneSteps) {
  for (const [i, title] of steps.entries()) {
    const after = await api(page, "POST", `/api/tasks/${taskId}/steps`, { title });
    const step = after.steps ? after.steps[after.steps.length - 1] : after;
    if (i < doneSteps) await api(page, "PATCH", `/api/tasks/${taskId}/steps/${step.id}`, { done: true });
  }
}

async function seedRecords(page, bots) {
  const projects = [];
  for (const p of PROJECTS) projects.push(await api(page, "POST", "/api/projects", { ...p, start_date: day(-60), due_date: day(150) }));
  for (const [title, due, priority, pIdx, steps, doneSteps, slice] of TASKS) {
    const project = pIdx === null ? null : projects[pIdx];
    const task = await api(page, "POST", "/api/tasks", { title, priority, due_date: due === null ? null : day(due),
      project_id: project?.id ?? null, allocated_budget: project && slice ? slice : null });
    await seedSteps(page, task.id, steps, doneSteps);
  }
  for (const [offset, amount, note, pIdx] of EXPENSES) {
    const project = pIdx === null ? null : projects[pIdx];
    await api(page, "POST", "/api/money/expenses", { amount, note, spent_at: day(offset), project_id: project?.id ?? null });
  }
  const routines = {};
  for (const { bot, name, schedule, instructions } of ROUTINES) {
    routines[name] = (await api(page, "POST", `/api/bots/${bots[bot]}/routines`, { name, instructions, schedule })).id;
  }
  return { projects, routines };
}

const detailPane = (page) => page.getByRole("main");

async function say(page, botName, text, delay = 0) {
  const box = detailPane(page).getByPlaceholder(`Message ${botName}`);
  if (delay) { await box.click(); await box.pressSequentially(text, { delay }); } else await box.fill(text);
  await page.waitForTimeout(delay ? 600 : 0);
  await box.press("Enter");
}

async function runChats(page, bots, routines) {
  await page.goto(`/bots/${bots.Chief}`);
  await say(page, "Chief", MESSAGES.chief);
  await detailPane(page).getByRole("heading", { name: "This week" }).waitFor(SLOW);
  await page.goto(`/bots/${bots["Social media"]}`);
  await say(page, "Social media", MESSAGES.social);
  await detailPane(page).getByText("Autumn in a cup.").waitFor(SLOW);
  await api(page, "POST", `/api/routines/${routines["Morning orders check"]}/run-now`);
  await page.goto(`/bots/${bots.Bookkeeper}`);
  await detailPane(page).getByRole("article", { name: /^Report:/ }).first().waitFor(SLOW);
}

// --- the demo video, which also takes the Pay card shot ------------------------------------------------------
// The fake computer's live screen is a flat placeholder (ROOST_DESK=fake has no VNC), so the video keeps to the chat.

async function recordDemo(browser, state, bots) {
  const dir = mkdtempSync(join(tmpdir(), "roost-readme-video-"));
  const context = await browser.newContext({ baseURL: BASE, viewport: DESKTOP, storageState: state,
    recordVideo: { dir, size: VIDEO_SIZE } });
  const page = await context.newPage();
  await page.goto(`/bots/${bots["Shop helper"]}`);
  await page.waitForTimeout(1500);
  await say(page, "Shop helper", MESSAGES.shop, 45);
  // A buy click in your own chat parks on the Pay card (Pay · Don't pay) with the button's picture.
  try { await detailPane(page).getByRole("img", { name: "The button: Buy now" }).waitFor(SLOW); } catch (err) {
    if (process.env.READMESHOTS_DEBUG) await page.screenshot({ path: process.env.READMESHOTS_DEBUG });
    throw err;
  }
  await page.waitForTimeout(2500);
  await shot(page, "computer-ask-card");
  const yes = detailPane(page).getByRole("button", { name: "Pay", exact: true });
  await yes.hover();
  await page.waitForTimeout(1200);
  await yes.click();
  await detailPane(page).getByText("order 1001 is placed", { exact: false }).waitFor(SLOW);
  await page.waitForTimeout(3000);
  await page.getByRole("link", { name: "Workspace", exact: true }).first().click();
  await detailPane(page).getByRole("heading", { name: "Workspace", exact: true }).waitFor(SLOW);
  await page.waitForTimeout(3500);
  const video = page.video();
  await context.close();
  renameSync(await video.path(), join(OUT, "demo.webm"));
  rmSync(dir, { recursive: true, force: true });
}

// --- the screenshots -------------------------------------------------------------------------------------------

async function shot(page, name) {
  await page.waitForLoadState("networkidle").catch(() => {});
  await page.waitForTimeout(900);
  await page.mouse.move(0, 0);
  await page.screenshot({ path: join(OUT, `${name}.png`) });
}

async function desktopShots(browser, state, bots, projects) {
  const context = await browser.newContext({ baseURL: BASE, viewport: DESKTOP, storageState: state });
  const page = await context.newPage();
  await page.goto(`/bots/${bots["Social media"]}`); await shot(page, "home");   // the sidebar, beside a chat
  await page.goto(`/bots/${bots.Chief}`); await shot(page, "chat");
  await page.goto("/board?tab=tasks&project=all"); await shot(page, "board-tasks");
  await page.goto("/board?tab=money"); await shot(page, "board-money");
  await page.goto(`/board/projects/${projects[0].id}`); await shot(page, "project");
  await page.goto("/routines"); await shot(page, "routines");
  await context.close();
}

async function phoneShots(browser, state, bots) {
  const context = await browser.newContext({ baseURL: BASE, viewport: PHONE, deviceScaleFactor: 1, isMobile: true,
    hasTouch: true, storageState: state });
  const page = await context.newPage();
  await page.goto(`/bots/${bots.Chief}`);
  await detailPane(page).getByText(MESSAGES.chief).waitFor(SLOW);
  await page.waitForTimeout(900);   // the chat settles at its end first; then show the question with its answer
  await detailPane(page).getByText(MESSAGES.chief).evaluate((el) => el.scrollIntoView({ block: "start" }));
  await shot(page, "phone-chat");
  await page.goto("/board?tab=tasks&project=all"); await shot(page, "phone-tasks");
  await page.goto("/"); await shot(page, "phone-home");
  await context.close();
}

// --- main ------------------------------------------------------------------------------------------------------

async function main() {
  diskGuard("screenshots");
  if (await portBusy()) throw new Error(`port ${PORT} is busy: stop whatever runs there first`);
  ensureWebBuilt();
  mkdirSync(OUT, { recursive: true });
  const require = createRequire(join(WEB, "package.json"));
  const { chromium } = require("@playwright/test");
  const gateway = startGateway();
  const browser = await chromium.launch();
  try {
    await waitUp();
    const context = await browser.newContext({ baseURL: BASE, viewport: DESKTOP });
    const page = await context.newPage();
    await signUp(page);
    const bots = await seedBots(page);
    const { projects, routines } = await seedRecords(page, bots);
    await runChats(page, bots, routines);
    const state = await context.storageState();
    await context.close();
    await recordDemo(browser, state, bots);
    await desktopShots(browser, state, bots, projects);
    await phoneShots(browser, state, bots);
  } finally {
    await browser.close();
    try { process.kill(-gateway.pid, "SIGTERM"); } catch { /* already gone */ }
  }
}

main().then(() => console.log(`screenshots and demo.webm in ${OUT}`), (err) => { console.error(err); process.exitCode = 1; });
