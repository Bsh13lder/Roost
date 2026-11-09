import { useState, type FormEvent } from "react";
import { Button } from "../../ui/Button";
import {
  TOUCH_KEY_ORDER, TOUCH_SEND_LABEL, TOUCH_TYPE_LABEL, TOUCH_TYPE_MAX_CHARS, type TouchKey,
} from "./constants";

export interface LiveControls {
  typeText: (text: string) => void;
  pressKey: (key: TouchKey) => void;
}

// Take control on a touch screen: a phone has no keyboard noVNC can hear, so text is typed here and sent into the
// computer through its clipboard, with Enter, Backspace, Tab and Escape as buttons. Nothing typed is kept.
export function TouchKeys({ controls }: { controls: LiveControls }) {
  const [text, setText] = useState("");
  const send = (event: FormEvent) => {
    event.preventDefault();
    if (!text) return;
    controls.typeText(text);
    setText("");
  };
  return (
    <form className="touch-keys" onSubmit={send}>
      <input className="touch-keys__field" type="text" value={text} aria-label={TOUCH_TYPE_LABEL}
        placeholder={TOUCH_TYPE_LABEL} maxLength={TOUCH_TYPE_MAX_CHARS} autoComplete="off" autoCorrect="off"
        autoCapitalize="off" spellCheck={false} onChange={(event) => setText(event.target.value)} />
      <Button type="submit" variant="primary" size="md" disabled={!text}>{TOUCH_SEND_LABEL}</Button>
      <div className="touch-keys__keys">
        {TOUCH_KEY_ORDER.map((key) => (
          <Button key={key} variant="secondary" size="md" onClick={() => controls.pressKey(key)}>{key}</Button>
        ))}
      </div>
    </form>
  );
}
