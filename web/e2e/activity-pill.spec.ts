import { expect, test, type Page, type WebSocketRoute } from "@playwright/test";
import { api, botIdFromUrl, createBot, detailPane, say, signIn } from "./helpers";

// The activity pill (docs/plans/2026-10-23-roost-activity-pill.md). The events socket is passed through to the
// scripted gateway, and the test adds a run's run_step frames on top, so each state holds still long enough to
// check (and, with PILL_SHOTS=<dir>, to photograph at a desktop and a phone width): Thinking, browsing a site,
// running a program, the folded line, and the sheet with every step and no code.
const SHOTS = process.env.PILL_SHOTS;
const DESKTOP = { width: 1440, height: 900 };
const PHONE = { width: 390, height: 844 };
const SLOW = { timeout: 30_000 };

async function shot(page: Page, name: string) {
  if (!SHOTS) return;
  for (const [label, size] of [["1440", DESKTOP], ["390", PHONE]] as const) {
    await page.setViewportSize(size);
    await page.waitForTimeout(300);
    await page.screenshot({ path: `${SHOTS}/${name}-${label}.png` });
  }
  await page.setViewportSize(DESKTOP);
}

test("the pill says what the bot is doing in words, folds into a line, and opens the steps", async ({ page }) => {
  test.setTimeout(120_000);
  let socket: WebSocketRoute | null = null;
  await page.routeWebSocket(/\/api\/events/, (ws) => {
    socket = ws;
    ws.connectToServer();
  });
  await page.setViewportSize(DESKTOP);
  await signIn(page);
  await createBot(page, "Gela", "Looks things up for me");
  const botId = botIdFromUrl(page);
  await say(page, "Gela", "Is WhatsApp Web up?");
  const detail = detailPane(page);
  await expect(detail.getByText("Is WhatsApp Web up?")).toBeVisible(SLOW);
  await page.waitForTimeout(1500); // the scripted reply settles
  const thread = (await api(page, "POST", `/api/bots/${botId}/chat`)) as { id: string };

  let seq = 1_000_000;
  const send = (frame: Record<string, unknown>) => {
    seq += 1;
    socket?.send(JSON.stringify({ seq, ...frame }));
  };
  const step = (n: number, kind: string, line: string, state: string, at: string, host: string | null = null) =>
    send({ type: "run_step", bot_id: botId, thread_id: thread.id, run_id: "shot-run", step: n, kind, line, host,
      at: `2026-10-23T20:00:${at}Z`, state });
  const status = (value: string) => send({ type: "bot_status", bot_id: botId, status: value, activity: null });

  status("on_it");
  step(1, "think", "Thinking", "start", "00");
  const pill = detail.getByTestId("activity-pill").last();
  await expect(pill).toContainText("Thinking…", SLOW);
  await shot(page, "1-thinking");

  step(1, "think", "Thinking", "done", "02");
  step(2, "read", "Opened web.whatsapp.com", "start", "02", "web.whatsapp.com");
  await expect(pill).toContainText("Browsing web.whatsapp.com…");
  await shot(page, "2-browsing");

  step(2, "read", "Opened web.whatsapp.com", "done", "15", "web.whatsapp.com");
  step(3, "program", "Checked that web.whatsapp.com answers", "start", "15", "web.whatsapp.com");
  await expect(pill).toContainText("Checking that web.whatsapp.com answers…");
  await expect(pill).toContainText("2");
  await shot(page, "3-program");

  step(3, "program", "Checked that web.whatsapp.com answers", "done", "38", "web.whatsapp.com");
  step(4, "message", "Writing the reply", "start", "38");
  step(4, "message", "Writing the reply", "done", "42");
  status("resting");
  const line = detail.getByTestId("activity-line").last();
  await expect(line).toContainText("Worked for 42 s · 2 steps", SLOW);
  await shot(page, "4-finished");

  await line.click();
  const sheet = page.getByRole("dialog", { name: "What Gela did" });
  await expect(sheet).toBeVisible(SLOW);
  await expect(sheet).toContainText("Opened web.whatsapp.com");
  await expect(sheet).toContainText("Checked that web.whatsapp.com answers");
  await expect(sheet).not.toContainText("curl");
  await shot(page, "5-sheet");
});
