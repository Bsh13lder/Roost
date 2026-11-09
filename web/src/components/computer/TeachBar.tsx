import { useState } from "react";
import { Button } from "../../ui/Button";
import { useToast } from "../../ui/Toast";
import * as teachApi from "../../api/teach";
import { describeError } from "../../api/client";
import type { BotOut } from "../../api/types";
import { TeachDoneForm } from "./TeachDoneForm";
import { TEACH_DISCARDED_TEXT, TEACH_PROPOSED_TEXT } from "./constants";

interface TeachBarProps {
  bot: BotOut;
  onClosed: () => void; // teaching ended and the computer was given back
}

// The control bar while you teach: "You're teaching" and I'm done teaching (with an optional description).
// Only clicks and which field you typed into are recorded, never what you type.
export function TeachBar({ bot, onClosed }: TeachBarProps) {
  const toast = useToast();
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const stop = async (body: teachApi.TeachStopIn) => {
    setBusy(true);
    setError(null);
    try {
      const outcome = await teachApi.stopTeach(bot.id, body);
      toast.show(outcome.discarded ? TEACH_DISCARDED_TEXT : TEACH_PROPOSED_TEXT);
      onClosed();
    } catch (err) {
      setError(describeError(err));
      setBusy(false);
    }
  };
  if (asking) {
    return (
      <TeachDoneForm busy={busy} error={error}
        onConfirm={(description) => void stop(description ? { description } : {})}
        onDiscard={() => void stop({ discard: true })}
        onBack={() => { setAsking(false); setError(null); }} />
    );
  }
  return (
    <>
      <span className="control-screen__state">
        You&apos;re teaching {bot.name}. Clicks and field names are recorded, never what you type.
      </span>
      <Button variant="primary" size="md" onClick={() => setAsking(true)}>I&apos;m done teaching</Button>
    </>
  );
}
