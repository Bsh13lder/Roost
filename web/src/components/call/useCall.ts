import { useCallback, useEffect, useRef, useState } from "react";
import { CallMachine, INITIAL_CALL_VIEW, type CallInputs, type CallPhase, type CallViewState } from "./callMachine";

export type { CallInputs, CallPhase } from "./callMachine";
export { NOT_CAUGHT_TEXT } from "./callConstants";

// Talking over the bot while it speaks, when the browser really cancels the speaker's echo. Off here, the mic is
// simply off while the bot speaks, as it is without echo cancellation.
export const CALL_BARGE_IN = true;

export interface CallView extends CallViewState {
  readonly toggleMute: () => void;
  readonly interrupt: () => void;
  readonly orbTap: () => void;
}

// A call (voice call mode): the machine in callMachine.ts does the work; this binds it to React. It opens once per
// mount, hears every change of the chat it is handed, and closes with the screen.
export function useCall(inputs: CallInputs): CallView {
  const [view, setView] = useState<CallViewState>(INITIAL_CALL_VIEW);
  const latest = useRef(inputs);
  latest.current = inputs;
  const machine = useRef<CallMachine | null>(null);

  useEffect(() => {
    const made = new CallMachine(() => latest.current, setView, { bargeIn: CALL_BARGE_IN });
    machine.current = made;
    void made.open();
    return () => {
      made.close();
      if (machine.current === made) machine.current = null;
    };
  }, []);

  const { messages, bot, approvals, stuck, streaming, speechReady } = inputs;
  useEffect(() => { machine.current?.update(); }, [messages, bot, approvals, stuck, streaming, speechReady]);

  const toggleMute = useCallback(() => machine.current?.toggleMute(), []);
  const interrupt = useCallback(() => machine.current?.interrupt(), []);
  const orbTap = useCallback(() => machine.current?.orbTap(), []);
  return { ...view, toggleMute, interrupt, orbTap };
}
