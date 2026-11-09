import { useState } from "react";
import { ErrorNotice } from "../ErrorNotice";
import { describeError } from "../../api/client";
import { setBotVoice, type VoiceInfo } from "../../api/voice";
import type { BotOut, BotVoice } from "../../api/types";
import { useVoiceInfo } from "../../lib/voiceInfo";
import { playSample, sampleKey, speechErrorText, toggleSpeech, useSpeechPhase } from "../../store/speech";
import { Button } from "../../ui/Button";
import { Select } from "../../ui/Select";
import { Switch } from "../../ui/Switch";

export const VOICE_OFF_LINE = "Voice isn't running on your Mac yet.";
export const READ_ALOUD_LABEL = "Read replies aloud";
export const CORRECT_LABEL = "Correct what I say";
export const CORRECT_HINT = "Shows a corrected copy of what you say, in any language, with the mistakes marked: names, numbers, sites and grammar.";
export const LANGUAGE_LABEL = "I speak";
export const TRY_IT_LABEL = "Try it";
export const AUTO_LANGUAGE = "auto";
// The server's defaults (roost/voice/constants.py DEFAULT_VOICE), for a bot an older server sent without a voice.
export const DEFAULT_VOICE: BotVoice = {
  speaker: "aiden", tone: "natural", speed: 1, read_aloud: false, correct_speech: false, correct_english: false, language: AUTO_LANGUAGE,
};

// The bot's voice with every field present: an older server's bot has only correct_english (or neither), which
// reads into the switch; a bot with no language reads Auto-detect.
export function wholeVoice(voice: BotVoice | undefined): BotVoice {
  const correct = voice?.correct_speech ?? voice?.correct_english ?? false;
  return { ...DEFAULT_VOICE, ...voice, correct_speech: correct, correct_english: correct, language: voice?.language ?? AUTO_LANGUAGE };
}

// "1.25×", and whole numbers as "1.0×".
export const speedLabel = (speed: number) => `${Number.isInteger(speed) ? speed.toFixed(1) : String(speed)}×`;

// What the Voice fold shows while closed: the voice's name.
export function voiceSummary(info: VoiceInfo | null, voice: BotVoice | undefined): string | undefined {
  return info?.speakers.find((speaker) => speaker.id === (voice ?? DEFAULT_VOICE).speaker)?.name;
}

function TryIt({ botId, voice, disabled }: { botId: string; voice: BotVoice; disabled: boolean }) {
  const phase = useSpeechPhase(sampleKey(botId));
  const [error, setError] = useState<string | null>(null);
  const run = () => {
    setError(null);
    toggleSpeech(sampleKey(botId), () => playSample(botId, voice.speaker, voice.tone, voice.speed))
      .catch((err: unknown) => setError(speechErrorText(err)));
  };
  return (
    <div className="info-row voice__try">
      <Button size="sm" disabled={disabled} loading={phase === "loading"} onClick={run}>
        {phase === "playing" ? "Stop" : TRY_IT_LABEL}
      </Button>
      {error ? <ErrorNotice message={error} /> : null}
    </div>
  );
}

function VoiceControls({ bot, info, onChange }: { bot: BotOut; info: VoiceInfo; onChange: (bot: BotOut) => void }) {
  const [error, setError] = useState<string | null>(null);
  const off = !info.available;
  const voice = wholeVoice(bot.voice);
  const save = async (next: BotVoice) => {
    setError(null);
    try {
      onChange(await setBotVoice(bot.id, { ...next, correct_english: next.correct_speech }));
    } catch (err) {
      setError(describeError(err));
    }
  };
  const speakers = info.speakers.map((s) => ({ value: s.id, label: s.name, hint: `best in ${s.best_in}` }));
  const tones = info.tones.map((t) => ({ value: t.id, label: t.name }));
  const speeds = info.speeds.map((speed) => ({ value: String(speed), label: speedLabel(speed) }));
  const languages = (info.languages ?? []).map((lang) => ({ value: lang.id, label: lang.name }));
  return (
    <div className="voice">
      {off ? <p className="info-row__hint voice__off">{VOICE_OFF_LINE}</p> : null}
      <div className="info-row info-row--select">
        <span className="info-row__label">Voice</span>
        <Select label="Voice" size="md" value={voice.speaker} options={speakers} disabled={off}
          onChange={(speaker) => void save({ ...voice, speaker })} />
      </div>
      <div className="info-row info-row--select">
        <span className="info-row__label">Tone</span>
        <Select label="Tone" size="md" value={voice.tone} options={tones} disabled={off}
          onChange={(tone) => void save({ ...voice, tone })} />
      </div>
      <div className="info-row info-row--select">
        <span className="info-row__label">Speed</span>
        <Select label="Speed" size="md" value={String(voice.speed)} options={speeds} disabled={off}
          onChange={(speed) => void save({ ...voice, speed: Number(speed) })} />
      </div>
      {languages.length > 0 ? (
        <div className="info-row info-row--select">
          <span className="info-row__label">{LANGUAGE_LABEL}</span>
          <Select label={LANGUAGE_LABEL} size="md" value={voice.language ?? AUTO_LANGUAGE} options={languages} disabled={off}
            onChange={(language) => void save({ ...voice, language })} />
        </div>
      ) : null}
      <div className="info-row info-row--switch">
        <Switch checked={voice.read_aloud} disabled={off} onChange={(read_aloud) => void save({ ...voice, read_aloud })}>
          {READ_ALOUD_LABEL}
        </Switch>
      </div>
      <div className="info-row info-row--switch voice__correct">
        <Switch checked={voice.correct_speech === true} disabled={off}
          onChange={(correct_speech) => void save({ ...voice, correct_speech })}>
          {CORRECT_LABEL}
        </Switch>
        <p className="info-row__hint">{CORRECT_HINT}</p>
      </div>
      <TryIt botId={bot.id} voice={voice} disabled={off} />
      {error ? <div className="info-row"><ErrorNotice message={error} /></div> : null}
    </div>
  );
}

// The Voice fold (voice plan V3, voice tuning D2/D3): Voice, Tone, Speed, I speak (Auto-detect or a language the
// ear supports), Read replies aloud, Correct what I say and Try it. Each change saves the whole object at once.
// With the Mac's voice service off, one quiet line says so and the controls stay readable, disabled.
export function VoiceSection({ bot, onChange }: { bot: BotOut; onChange: (bot: BotOut) => void }) {
  const state = useVoiceInfo();
  if (state.status === "loading") return <p className="skills__loading">Loading the voices&hellip;</p>;
  if (state.status === "failed") return <div className="info-row"><ErrorNotice message={state.error} /></div>;
  return <VoiceControls bot={bot} info={state.info} onChange={onChange} />;
}
