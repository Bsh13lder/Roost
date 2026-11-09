import { useEffect, useState } from "react";
import { getUsage } from "../../api/usage";
import { tokensLine } from "../../lib/tokenCount";

const WEEK_DAYS = 7;

// Home's quiet line (token usage plan): "Tokens today: N · this week: M · busiest: <bot>". It is a nicety, so a
// failed load (or an older server with no totals) hides it instead of showing an error.
export function TokensLine() {
  const [line, setLine] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    getUsage(WEEK_DAYS)
      .then((usage) => {
        if (!live || !usage.total || !usage.today_total) return;
        setLine(tokensLine(usage.today_total.tokens, usage.total.tokens, usage.busiest?.name ?? null));
      })
      .catch((err: unknown) => { console.warn("Could not load the token usage.", err); });
    return () => { live = false; };
  }, []);
  if (line === null) return null;
  return <p className="tokens-line">{line}</p>;
}
