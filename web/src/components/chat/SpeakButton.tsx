import { messageKey, speakMessage, speechErrorText, toggleSpeech, useSpeechPhase } from "../../store/speech";
import { useVoiceInfo, voiceAvailable } from "../../lib/voiceInfo";
import { IconButton } from "../../ui/IconButton";
import { useOptionalToast } from "../../ui/Toast";
import { SpeakerIcon, StopIcon } from "../icons";

export const SPEAK_LABEL = "Read aloud";
export const SPEAK_STOP_LABEL = "Stop reading";

// The speaker on a bot's reply or Report (voice plan V3): plays it in the bot's voice, part by part; tapping again
// stops. Shown only when the Mac's voice service answers.
export function SpeakButton({ threadId, messageId }: { threadId: string; messageId: string }) {
  const info = useVoiceInfo();
  const phase = useSpeechPhase(messageKey(messageId));
  const toast = useOptionalToast();
  if (!voiceAvailable(info)) return null;
  const onClick = () => {
    toggleSpeech(messageKey(messageId), () => speakMessage(threadId, messageId)).catch((err: unknown) => {
      const words = speechErrorText(err);
      if (toast) toast.show(words, { tone: "danger" });
      else console.warn(words, err);
    });
  };
  const label = phase === "idle" ? SPEAK_LABEL : SPEAK_STOP_LABEL; // loading is busy, and tapping it stops too
  return (
    <IconButton label={label} tooltip={false} size="sm" className="speak-btn" data-phase={phase} aria-busy={phase === "loading" || undefined}
      icon={phase === "idle" ? <SpeakerIcon /> : <StopIcon />} onClick={onClick} />
  );
}
