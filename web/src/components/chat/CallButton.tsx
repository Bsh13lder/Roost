import { unlockAudio } from "../../lib/audioUnlock";
import { canRecord } from "../../lib/recorder";
import { useVoiceInfo, type VoiceInfoState } from "../../lib/voiceInfo";
import { unlockSpeech } from "../../store/speech";
import { WaveIcon } from "../icons";

export const NEEDS_HTTPS_TEXT = "Voice needs https";
export const VOICE_OFF_TEXT = "Voice isn't running on your Mac yet";

// Why Call can't be tapped right now, or null when it can. While the server's answer is unknown (loading, or the
// request failed) Call stays enabled and the call's own warm-up step reports what it finds.
export function callBlocker(info: VoiceInfoState): string | null {
  if (!canRecord()) return NEEDS_HTTPS_TEXT;
  if (info.status === "ready" && !info.info.available) return VOICE_OFF_TEXT;
  return null;
}

// The round Call in place of Send while the box is empty (call mode). It never silently becomes Send: when this
// browser can't record or the Mac's voice is off, it shows disabled and says why. The tap itself unlocks the
// browser's audio and the speaker (both need a user's gesture) before the call screen opens.
export function CallButton({ name, onCall }: { name: string; onCall: () => void }) {
  const info = useVoiceInfo();
  const blocker = callBlocker(info);
  const onClick = async () => {
    await Promise.allSettled([unlockAudio(), unlockSpeech()]);
    onCall();
  };
  const label = blocker ?? `Call ${name}`;
  return (
    <button type="button" className="composer__send composer__call" data-testid="call" onClick={() => void onClick()}
      disabled={blocker !== null} aria-label={label} title={label}>
      <WaveIcon />
    </button>
  );
}
