import type { KeyboardEvent } from "react";

// What Safari reports for a key the input method (IME) is still handling.
const IME_KEY_CODE = 229;

// The composers' send key (redesign P2): Enter sends and Shift+Enter is a new line. The Enter that
// confirms a word in Japanese, Chinese or Korean input belongs to the IME and never sends half a message.
export function isSendKey(event: KeyboardEvent<HTMLTextAreaElement>): boolean {
  if (event.key !== "Enter" || event.shiftKey) return false;
  return !(event.nativeEvent.isComposing || event.keyCode === IME_KEY_CODE);
}
