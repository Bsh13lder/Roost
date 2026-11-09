import { useMicRecorder, type MicOptions } from "../../hooks/useMicRecorder";
import { canRecord } from "../../lib/recorder";
import { useVoiceInfo, voiceAvailable } from "../../lib/voiceInfo";
import { IconButton } from "../../ui/IconButton";
import { CloseIcon, MicIcon, StopIcon } from "../icons";

export const MIC_LABEL = "Speak a message";
export const MIC_STOP_LABEL = "Stop recording";
export const MIC_CANCEL_LABEL = "Cancel recording";
export const LISTENING_TEXT = "Listening…";
export const CHECKING_TEXT = "Checking…";

export interface MicButtonProps extends MicOptions {
  onText: (text: string) => void; // the words you said, for the composer (never sent by itself)
  onError: (message: string) => void;
  disabled?: boolean;
}

const clock = (seconds: number) => `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;

function MicControls({ onText, onError, disabled = false, ...options }: MicButtonProps) {
  const mic = useMicRecorder(onText, onError, options);
  const recording = mic.phase === "recording";
  const waiting = mic.phase === "listening" || mic.phase === "checking";
  return (
    <div className="mic" data-phase={mic.phase}>
      {recording ? (
        <>
          <span className="mic__rec" role="timer" aria-label="Recording">
            <span className="mic__dot" aria-hidden="true" />
            <span className="mic__time">{clock(mic.seconds)}</span>
          </span>
          <IconButton label={MIC_CANCEL_LABEL} tooltip={false} size="sm" icon={<CloseIcon />} onClick={mic.cancel}
            className="mic__cancel" />
        </>
      ) : null}
      {waiting ? <span className="mic__listening" role="status">{mic.phase === "checking" ? CHECKING_TEXT : LISTENING_TEXT}</span> : null}
      <IconButton label={recording ? MIC_STOP_LABEL : MIC_LABEL} tooltip={false} icon={recording ? <StopIcon /> : <MicIcon />}
        className="mic__button"
        disabled={disabled || mic.phase === "starting" || waiting} onClick={mic.toggle} />
    </div>
  );
}

// The composer's mic (voice plan V3): shown only when the Mac's voice service answers and this browser can record.
export function MicButton(props: MicButtonProps) {
  const info = useVoiceInfo();
  if (!voiceAvailable(info) || !canRecord()) return null;
  return <MicControls {...props} />;
}
