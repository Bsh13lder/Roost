import { expect, test } from "@playwright/test";
import { createBot, detailPane, signIn } from "./helpers";

// Call mode against the gateway's fake voice (ROOST_VOICE=fake hears every turn as "Add milk to my list" and speaks
// silence). Headless Chromium here can't open even its fake capture device (getUserMedia never settles), so the page's
// getUserMedia alone is replaced: it hands back a stream from Web Audio that plays a second of quiet, about a second of
// a voice-like sound (a tone that rises and falls four times a second), then quiet, which ends the turn. Everything
// after the device is the real thing: the audio graph, the endpointer, the WAV, transcribe, send, the reply and its
// speech. "Echo" has no script, so it answers "I heard: …".
test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    const fakeVoice = async (): Promise<MediaStream> => {
      const context = new AudioContext();
      const out = context.createMediaStreamDestination();
      const tone = context.createOscillator();
      tone.frequency.value = 220;
      const wobble = context.createOscillator();
      wobble.frequency.value = 4;
      const depth = context.createGain();
      depth.gain.value = 0.15;
      const level = context.createGain();
      level.gain.value = 0;
      wobble.connect(depth).connect(level.gain);
      tone.connect(level).connect(out);
      const start = context.currentTime + 1.0;
      level.gain.setValueAtTime(0.3, start);
      level.gain.setValueAtTime(0, start + 1.2);
      depth.gain.setValueAtTime(0, start + 1.2);
      tone.start();
      wobble.start();
      return out.stream;
    };
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: { getUserMedia: fakeVoice, enumerateDevices: async () => [] },
    });
  });
});

const NAME = "Echo";

test("a call hears you, sends your words and speaks the reply", async ({ page }) => {
  await signIn(page);
  await createBot(page, NAME, "Repeats what you say");
  const pane = detailPane(page);
  const warm = page.waitForResponse((r) => new URL(r.url()).pathname === "/api/voice/warm");
  const heard = page.waitForResponse((r) => new URL(r.url()).pathname === "/api/voice/transcribe", { timeout: 20_000 });
  const part = page.waitForResponse((r) => /\/speech\/0$/.test(new URL(r.url()).pathname), { timeout: 30_000 });
  await pane.getByRole("button", { name: `Call ${NAME}` }).click();
  const call = page.getByRole("dialog", { name: `Call with ${NAME}` });
  await expect(call).toBeVisible();
  expect((await warm).status()).toBe(200);
  expect((await heard).status()).toBe(200);
  await expect(call.getByText("Add milk to my list")).toBeVisible();
  expect((await part).status()).toBe(200);
  await expect(call.getByTestId("call-status")).toHaveText("Listening", { timeout: 20_000 });

  await call.getByRole("button", { name: "End call" }).click();
  await expect(call).toHaveCount(0);
  await expect(pane.locator("li.message--bot").filter({ hasText: "I heard: Add milk to my list" })).toHaveCount(1);
});
