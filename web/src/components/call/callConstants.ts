// The call's clocks (call mode, contract E and the shared contract): one place for every number the call screen
// times by. The phone mirrors them.

export const CALL_HEARTBEAT_MS = 20_000; // VOICE_CALL_HEARTBEAT_S: the server forgets a call 60 s after its last beat
export const CALL_HEARING_TIMEOUT_MS = 20_000; // CALL_HEARING_TIMEOUT_S: a transcription that takes longer is cut off
export const CALL_THINKING_TIMEOUT_MS = 120_000; // CALL_THINKING_TIMEOUT_S: a bot that never answers
export const CALL_STILL_ON_IT_AFTER_MS = 15_000; // CALL_STILL_ON_IT_AFTER_S: the first "Still on it."
export const CALL_STILL_ON_IT_EVERY_MS = 30_000; // then every 30 s...
export const CALL_STILL_ON_IT_MAX = 3; // ...at most this many times
export const SPEAKER_TAIL_MS = 300; // after the bot's last word, before the mic listens again (the speaker's tail)

export const WAKING_TEXT = "Waking the voice up…";
export const NOT_CAUGHT_TEXT = "I didn't catch that.";
export const SAY_AGAIN_TEXT = "Say that again?";
export const TAP_TO_LISTEN_TEXT = "Tap to start listening";
export const TAP_TO_HEAR_TEXT = "Tap to hear";
export const tooLongText = (botName: string) => `${botName} is taking long. Ask again, or wait for the reply in the chat.`;
