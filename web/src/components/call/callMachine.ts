// A call with a bot (voice call mode), as one small machine the screen's hook drives: open warms the Mac's voice
// and the microphone together and starts the call on the server (a beat every 20 s); a turn is heard, sent as your
// own message with the call flag, and the reply is spoken as it streams (live speech, contract B) or, on an old
// server, once it is stored; fixed lines (contract C) greet you, say "I didn't catch that", "Still on it" and bye;
// a goodbye word ends the call without sending. The mic is off while the bot is heard and thinks; while it speaks
// it is guarded when the browser cancels the speaker's echo (talking over the bot stops it), off otherwise.
import { ApiError, describeError } from "../../api/client";
import type { ApprovalCardOut, BotOut, MessageOut, StuckCardOut } from "../../api/types";
import { endCall, startCall, transcribe, warmVoice, type VoiceLineKey } from "../../api/voice";
import { takeUnlockedContext } from "../../lib/audioUnlock";
import { createLevelMeter, type LevelMeter } from "../../lib/callLevel";
import { openCallMic, type CallMic, type CallMicHandlers, type CallMicMode } from "../../lib/callMic";
import { createBeat, createTimerSlot } from "../../lib/callTimers";
import { askingLine, askingTitle, replyPlaceholder, turnOutcome } from "../../lib/callTurn";
import { isGoodbye } from "../../lib/callWords";
import { shownReply } from "../../lib/onItLead";
import type { SpeechReady } from "../../store/live";
import {
  LiveSpeechUnavailable, isSoundBlocked, speakLine, speakLive, speakMessage, speechErrorText, stopSpeech,
  type LiveSource,
} from "../../store/speech";
import {
  CALL_HEARING_TIMEOUT_MS, CALL_HEARTBEAT_MS, CALL_STILL_ON_IT_AFTER_MS, CALL_STILL_ON_IT_EVERY_MS,
  CALL_STILL_ON_IT_MAX, CALL_THINKING_TIMEOUT_MS, NOT_CAUGHT_TEXT, SAY_AGAIN_TEXT, SPEAKER_TAIL_MS,
  TAP_TO_HEAR_TEXT, TAP_TO_LISTEN_TEXT, WAKING_TEXT, tooLongText,
} from "./callConstants";

export type CallPhase = "warming" | "listening" | "hearing" | "thinking" | "speaking" | "failed";

export interface CallInputs {
  readonly bot: BotOut;
  readonly threadId: string;
  readonly messages: readonly MessageOut[];
  readonly approvals: readonly ApprovalCardOut[];
  readonly stuck: readonly StuckCardOut[];
  readonly streaming: Readonly<Record<string, string>>; // the live store's text as the reply streams
  readonly speechReady: Readonly<Record<string, SpeechReady>>; // the live store's speech_ready frames
  readonly send: (text: string, options: { call: true; spoken: true }) => Promise<string>; // your message's id
  readonly onClose: () => void;
}

export interface CallViewState {
  readonly phase: CallPhase;
  readonly muted: boolean;
  readonly level: number; // 0–1, for the orb
  readonly heard: string | null; // what you last said
  readonly heardId: string | null; // the id of your message that holds it, once sent (an english_fix line names it)
  readonly reply: string | null; // what the bot says, as it streams
  readonly note: string | null; // a quiet line under the words: a card waiting on you, a tap wanted, a failure
  readonly error: string | null; // why the call can't go on
}

export interface CallOptions {
  readonly bargeIn: boolean; // talk over the bot when the browser cancels its echo
}

export const INITIAL_CALL_VIEW: CallViewState = {
  phase: "warming", muted: false, level: 0, heard: null, heardId: null, reply: null, note: null, error: null,
};

interface Turn {
  readonly id: string; // your message
  readonly sawOnIt: boolean; // the bot has been On it since
  readonly replyId: string | null; // the reply being written, once its placeholder shows
  readonly stored: boolean; // the server has no live speech for it: speak it once stored
}

const NO_PARTS: SpeechReady = { parts: 0, done: false };
const isVoiceOff = (err: unknown) => err instanceof ApiError && err.status === 503;
const isOldServer = (err: unknown) => err instanceof ApiError && err.status === 404;
const quietly = (what: string) => (err: unknown) => { if (!isOldServer(err)) console.warn(what, err); };

export class CallMachine {
  private view = INITIAL_CALL_VIEW;
  private mic: CallMic | null = null;
  private warm: Promise<boolean> = Promise.resolve(false);
  private turn: Turn | null = null;
  private speakRun = 0; // bumped by every start and stop of the bot's speech
  private stillCount = 0;
  private closed = false;
  private retrySpeech: (() => void) | null = null; // "Tap to hear": the browser refused the sound
  private beat: { stop: () => void } | null = null;
  private readonly hearing = createTimerSlot();
  private readonly thinking = createTimerSlot();
  private readonly still = createTimerSlot();
  private readonly tail = createTimerSlot();
  private readonly readyListeners = new Set<() => void>();
  private readonly meter: LevelMeter;

  constructor(
    private readonly inputs: () => CallInputs,
    private readonly publish: (view: CallViewState) => void,
    private readonly options: CallOptions = { bargeIn: true },
  ) {
    this.meter = createLevelMeter((level) => this.set({ level }));
  }

  private get phase(): CallPhase { return this.view.phase; }

  // Read afresh after an await (TypeScript keeps an earlier check's narrowing of `this.phase` across it).
  private phaseIs(phase: CallPhase): boolean { return this.view.phase === phase; }

  private set(patch: Partial<CallViewState>): void {
    this.view = { ...this.view, ...patch };
    this.publish(this.view);
  }

  // ---- Opening and closing ---------------------------------------------------------------------------------------

  async open(): Promise<void> {
    const { bot, threadId } = this.inputs();
    this.warm = this.warmUp(bot.id);
    this.beat = createBeat(() => { startCall(threadId).catch(quietly("The call's beat didn't reach the server.")); }, CALL_HEARTBEAT_MS);
    try {
      const made = await openCallMic(this.micHandlers(), takeUnlockedContext() ?? undefined);
      if (this.closed) { made.close(); return; }
      this.mic = made;
    } catch (err) {
      if (!this.closed) this.fail(err instanceof Error ? err.message : describeError(err));
      return;
    }
    this.set({ note: WAKING_TEXT });
    this.listen();
    this.audioStateChanged(this.mic.audioState());
    const warmed = await this.warm;
    if (this.closed || this.phase === "failed") return;
    if (this.view.note === WAKING_TEXT) this.set({ note: null });
    if (warmed) await this.say("greeting");
  }

  private warmUp(botId: string): Promise<boolean> {
    return warmVoice(botId).then(() => true).catch((err: unknown) => {
      if (isVoiceOff(err)) { if (!this.closed) this.fail(describeError(err)); return false; }
      console.warn("The voice didn't warm up; the call goes on.", err);
      return false;
    });
  }

  private micHandlers(): CallMicHandlers {
    return {
      onLevel: (level) => this.meter.push(level),
      onTurn: (wav) => { void this.onTurn(wav); },
      onBargeIn: () => this.onBargeIn(),
      onAudioState: (state) => this.audioStateChanged(state),
    };
  }

  close(): void {
    this.closed = true;
    this.beat?.stop();
    [this.hearing, this.thinking, this.still, this.tail].forEach((slot) => slot.clear());
    this.mic?.close();
    this.mic = null;
    stopSpeech();
    endCall(this.inputs().threadId).catch(quietly("The call's end didn't reach the server."));
  }

  private fail(message: string): void {
    this.mic?.close();
    this.mic = null;
    [this.hearing, this.thinking, this.still, this.tail].forEach((slot) => slot.clear());
    this.set({ phase: "failed", error: message });
  }

  // ---- The microphone ----------------------------------------------------------------------------------------------

  private setMic(mode: CallMicMode): void {
    this.mic?.setMode(mode);
    if (mode === "off") this.meter.reset();
  }

  private listeningMode(): CallMicMode { return this.view.muted ? "off" : "listening"; }

  private speakingMode(): CallMicMode {
    return this.options.bargeIn && this.mic?.echoCancellation ? "guarded" : "off";
  }

  private listen(): void {
    this.set({ phase: "listening" });
    this.setMic(this.listeningMode());
  }

  private audioStateChanged(state: AudioContextState): void {
    if (state !== "running") this.set({ note: TAP_TO_LISTEN_TEXT });
    else if (this.view.note === TAP_TO_LISTEN_TEXT) this.set({ note: null });
  }

  // A fixed line in the bot's voice; the mic is off meanwhile and comes back when the call is listening.
  private async say(key: VoiceLineKey): Promise<void> {
    if (this.closed) return;
    this.setMic("off");
    try {
      await speakLine(this.inputs().bot.id, key);
    } catch (err) {
      console.warn(`The line "${key}" couldn't be spoken.`, err);
    }
    if (!this.closed && this.phase === "listening") this.setMic(this.listeningMode());
  }

  // ---- Your turn ---------------------------------------------------------------------------------------------------

  private async onTurn(wav: Blob): Promise<void> {
    if (this.phase !== "listening") return;
    this.set({ phase: "hearing", note: null });
    this.setMic("off");
    await this.warm; // a turn heard while the voice wakes waits for it
    if (this.closed || !this.phaseIs("hearing")) return;
    const words = await this.transcribeWithin(wav);
    if (words !== null && !this.closed) await this.heard(words);
  }

  // The words, or null when the hearing failed and the call already said so.
  private async transcribeWithin(wav: Blob): Promise<string | null> {
    const controller = new AbortController();
    this.hearing.set(() => controller.abort(), CALL_HEARING_TIMEOUT_MS);
    try {
      const { text } = await transcribe(wav, controller.signal);
      return text.trim();
    } catch (err) {
      if (this.closed) return null;
      if (controller.signal.aborted) {
        this.set({ note: SAY_AGAIN_TEXT });
        this.listen();
        await this.say("say_again");
      } else if (isVoiceOff(err)) {
        this.fail(describeError(err));
      } else {
        this.set({ note: describeError(err) });
        this.listen();
      }
      return null;
    } finally {
      this.hearing.clear();
    }
  }

  private async heard(words: string): Promise<void> {
    if (!words) {
      this.set({ note: NOT_CAUGHT_TEXT });
      this.listen();
      await this.say("not_caught");
      return;
    }
    this.set({ heard: words, heardId: null, reply: null });
    if (isGoodbye(words)) {
      await this.say("bye");
      if (!this.closed) this.inputs().onClose();
      return;
    }
    this.set({ phase: "thinking" });
    this.startThinkingClocks();
    try {
      const id = await this.inputs().send(words, { call: true, spoken: true });
      if (this.closed) return;
      this.turn = { id, sawOnIt: false, replyId: null, stored: false };
      this.set({ heardId: id });
      this.update();
    } catch (err) {
      if (this.closed) return;
      this.finishTurn();
      this.set({ note: describeError(err) });
      this.listen();
    }
  }

  // ---- Thinking --------------------------------------------------------------------------------------------------

  private startThinkingClocks(): void {
    this.stillCount = 0;
    this.thinking.set(() => this.thinkingTimedOut(), CALL_THINKING_TIMEOUT_MS);
    this.still.set(() => { void this.stillOnIt(); }, CALL_STILL_ON_IT_AFTER_MS);
  }

  private finishTurn(): void {
    this.turn = null;
    this.thinking.clear();
    this.still.clear();
  }

  private thinkingTimedOut(): void {
    if (this.phase !== "thinking") return;
    this.finishTurn();
    this.set({ note: tooLongText(this.inputs().bot.name) });
    this.listen();
  }

  // "Still on it." while nothing has streamed yet; once words come, the bot speaks for itself.
  private async stillOnIt(): Promise<void> {
    if (this.phase !== "thinking") return;
    const replyId = this.turn?.replyId;
    if (replyId && this.inputs().streaming[replyId]) return;
    this.stillCount += 1;
    await this.say("still_on_it");
    if (this.stillCount < CALL_STILL_ON_IT_MAX && this.phase === "thinking") {
      this.still.set(() => { void this.stillOnIt(); }, CALL_STILL_ON_IT_EVERY_MS);
    }
  }

  // The chat changed (messages, the bot's status, streamed text, speech frames): what the turn becomes.
  update(): void {
    this.readyListeners.forEach((listener) => listener());
    const turn = this.turn;
    if (turn === null) return;
    const inputs = this.inputs();
    if (turn.replyId === null) {
      const placeholder = replyPlaceholder(inputs.messages, turn.id);
      if (placeholder) {
        this.turn = { ...turn, replyId: placeholder.id };
        this.startLive(placeholder.id);
      }
    }
    this.showCaption();
    if (this.phase !== "thinking" || this.turn === null) return;
    const sawOnIt = this.turn.sawOnIt || inputs.bot.status === "on_it";
    if (sawOnIt !== this.turn.sawOnIt) this.turn = { ...this.turn, sawOnIt };
    const outcome = turnOutcome(inputs.messages, this.turn.id, inputs.bot.status, sawOnIt);
    if (outcome === null) return;
    if (outcome.kind === "asking") {
      this.finishTurn();
      this.set({ note: askingLine(inputs.bot.name, askingTitle(inputs.approvals, inputs.stuck, inputs.bot.id)) });
      this.listen();
      void this.say("asking");
    } else if (outcome.kind === "done") {
      this.finishTurn();
      this.listen();
    } else if (this.turn.replyId === null || this.turn.stored) {
      this.speakStored(outcome.messageId); // else the live speech ends this turn
    }
  }

  private showCaption(): void {
    const replyId = this.turn?.replyId;
    if (!replyId) return;
    const inputs = this.inputs();
    const text = inputs.streaming[replyId] ?? inputs.messages.find((m) => m.id === replyId)?.body ?? "";
    const shown = shownReply(text);
    if (shown && shown !== this.view.reply) this.set({ reply: shown });
  }

  // ---- The bot speaks ----------------------------------------------------------------------------------------------

  private startSpeaking(): void {
    this.set({ phase: "speaking" });
    this.setMic(this.speakingMode());
  }

  private startLive(replyId: string): void {
    const run = ++this.speakRun;
    const { threadId } = this.inputs();
    const source: LiveSource = {
      ready: () => this.inputs().speechReady[replyId] ?? NO_PARTS,
      onChange: (listener) => {
        this.readyListeners.add(listener);
        return () => { this.readyListeners.delete(listener); };
      },
      settled: () => {
        const inputs = this.inputs();
        return inputs.messages.some((m) => m.id === replyId && m.seq > 0)
          || (this.turn?.sawOnIt === true && inputs.bot.status !== "on_it");
      },
      onPart: (index) => { if (index === 0 && run === this.speakRun) this.startSpeaking(); },
    };
    speakLive(threadId, replyId, source)
      .then(() => this.afterSpeaking(run))
      .catch((err: unknown) => this.speechFailed(err, run, () => this.startLive(replyId)));
  }

  private speakStored(messageId: string): void {
    const { threadId, messages } = this.inputs();
    const body = messages.find((m) => m.id === messageId)?.body;
    if (body) this.set({ reply: shownReply(body) });
    this.startSpeaking();
    const run = ++this.speakRun;
    speakMessage(threadId, messageId)
      .then(() => this.afterSpeaking(run))
      .catch((err: unknown) => this.speechFailed(err, run, () => this.speakStored(messageId)));
  }

  private speechFailed(err: unknown, run: number, retry: () => void): void {
    if (run !== this.speakRun || this.closed) return;
    if (err instanceof LiveSpeechUnavailable) {
      if (this.turn) this.turn = { ...this.turn, stored: true };
      this.update();
      return;
    }
    if (isSoundBlocked(err)) {
      this.retrySpeech = retry;
      this.set({ note: TAP_TO_HEAR_TEXT });
      return;
    }
    this.set({ note: speechErrorText(err) });
    this.afterSpeaking(run);
  }

  private afterSpeaking(run: number): void {
    if (run !== this.speakRun || this.closed) return;
    this.finishTurn();
    this.retrySpeech = null;
    this.tail.set(() => { if (!this.closed && this.phase !== "failed") this.listen(); }, SPEAKER_TAIL_MS);
  }

  private onBargeIn(): void {
    if (this.phase === "speaking" && this.speakingMode() === "guarded") this.interrupt();
  }

  // ---- What you do -------------------------------------------------------------------------------------------------

  interrupt(): void {
    if (this.phase !== "speaking") return;
    const replyId = this.turn?.replyId ?? null;
    this.speakRun += 1;
    stopSpeech();
    this.tail.clear();
    if (replyId) startCall(this.inputs().threadId, replyId).catch(quietly("The interruption didn't reach the server."));
    this.finishTurn();
    this.listen();
  }

  // The orb: wakes a suspended browser, retries a refused sound, sends now while listening, interrupts while speaking.
  orbTap(): void {
    if (this.mic && this.mic.audioState() !== "running") {
      this.mic.resume().catch((err: unknown) => console.warn("The browser's audio didn't resume.", err));
      return;
    }
    if (this.retrySpeech) {
      const retry = this.retrySpeech;
      this.retrySpeech = null;
      this.set({ note: null });
      retry();
      return;
    }
    if (this.phase === "listening") this.mic?.flush();
    else if (this.phase === "speaking") this.interrupt();
  }

  toggleMute(): void {
    const muted = !this.view.muted;
    this.set({ muted });
    if (this.phase === "listening") this.setMic(muted ? "off" : "listening");
  }
}
