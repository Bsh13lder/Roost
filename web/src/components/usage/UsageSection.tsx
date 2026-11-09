import { useEffect, useState } from "react";
import { describeError } from "../../api/client";
import { getBotUsage, type BotUsageOut } from "../../api/usage";
import { barHeights, compactCount } from "../../lib/tokenCount";
import { ErrorNotice } from "../ErrorNotice";

export const USAGE_DAYS = 7;

const tokensText = (n: number) => `${compactCount(n)} tokens`;

function UsageBars({ usage }: { usage: BotUsageOut }) {
  const heights = barHeights(usage.per_day.map((day) => day.tokens));
  return (
    <div className="usage__bars">
      {usage.per_day.map((day, i) => (
        <span key={day.day} className="usage__bar-slot" role="img" aria-label={`${day.day}: ${tokensText(day.tokens)}`}
          title={`${day.day}: ${tokensText(day.tokens)}`}>
          <span className="usage__bar" style={{ height: `${heights[i]}%` }} data-today={day.day === usage.today} />
        </span>
      ))}
    </div>
  );
}

// "Usage" on the bot's Settings (token usage plan): today, the last 7 days, in · out, and a bar per day.
// A lazy chunk, loaded when the fold opens.
export default function UsageSection({ botId }: { botId: string }) {
  const [usage, setUsage] = useState<BotUsageOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    getBotUsage(botId, USAGE_DAYS)
      .then((loaded) => { if (live) { setUsage(loaded); setError(null); } })
      .catch((err: unknown) => { if (live) setError(describeError(err)); });
    return () => { live = false; };
  }, [botId]);
  if (error) return <ErrorNotice message={error} />;
  if (usage === null) return <p className="usage__note">Loading the usage&hellip;</p>;
  if (usage.total.tokens === 0) return <p className="usage__note">No tokens used yet.</p>;
  return (
    <section className="info-card usage" aria-label="Usage">
      <dl className="usage__stats">
        <div><dt>Today</dt><dd>{tokensText(usage.today_total.tokens)}</dd></div>
        <div><dt>Last {USAGE_DAYS} days</dt><dd>{tokensText(usage.total.tokens)}</dd></div>
      </dl>
      <p className="usage__note">
        in {compactCount(usage.total.tokens_in)} · out {compactCount(usage.total.tokens_out)}
      </p>
      <UsageBars usage={usage} />
    </section>
  );
}
