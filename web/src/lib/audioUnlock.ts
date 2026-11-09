// The browser lets an AudioContext run only when it was made (and resumed) in a user's tap. The Call button makes
// one in its click and leaves it here; the call's microphone takes it when it opens a moment later.
import { canRecord } from "./recorder";

let unlocked: AudioContext | null = null;

// In the Call tap: make the context now and ask it to run. Never throws; without one the mic makes its own.
export async function unlockAudio(): Promise<void> {
  if (!canRecord()) return;
  try {
    const context = new AudioContext();
    unlocked = context;
    await context.resume();
  } catch (err) {
    console.info("The browser's audio wasn't unlocked by the tap; the call will ask for one.", err);
  }
}

// The context the last tap unlocked, once; null when there is none.
export function takeUnlockedContext(): AudioContext | null {
  const context = unlocked;
  unlocked = null;
  return context;
}
