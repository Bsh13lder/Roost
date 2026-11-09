import { useState } from "react";
import { stopBot } from "../../api/bots";
import { describeError } from "../../api/client";
import { Button } from "../../ui/Button";

// Steer: by the composer while the bot is On it. The run ends at its next step and the chat says what it did.
export function StopButton({ botId, name, onError }: {
  botId: string; name: string; onError: (message: string) => void;
}) {
  const [busy, setBusy] = useState(false);
  const stop = async () => {
    setBusy(true);
    try {
      await stopBot(botId);
    } catch (err) {
      onError(describeError(err));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="chat-stop">
      <Button variant="ghost" size="sm" loading={busy} onClick={() => void stop()} aria-label={`Stop ${name}`}>
        Stop
      </Button>
    </div>
  );
}
