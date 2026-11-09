import { useEffect, useState } from "react";
import { Switch } from "../../ui/Switch";
import { describeError } from "../../api/client";
import * as usageApi from "../../api/usage";
import type { BotOut } from "../../api/types";
import { ErrorNotice } from "../ErrorNotice";
import { FULL_LIMIT_LABEL, FULL_LIMIT_REFUSAL } from "../routines/constants";
import { zoneStamp } from "../routines/zoneTime";

const stillOn = (until: string | null) => until !== null && Date.parse(until) > Date.now();

// "Use the full limit until it resets" on the Info tab. Only this switch can turn it on, and only while Roost can read
// the usage limit (the 10% reserve needs it): with no reading it is disabled and says why.
export function FullLimitSwitch({ bot, onChange }: { bot: BotOut; onChange: (bot: BotOut) => void }) {
  const [readable, setReadable] = useState<boolean | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    usageApi.getUsage().then((usage) => { if (live) setReadable(usage.readable); }).catch(() => { if (live) setReadable(false); });
    return () => { live = false; };
  }, []);
  const on = stillOn(bot.full_limit_until);
  const toggle = async (next: boolean) => {
    setError(null);
    try {
      onChange(await usageApi.setFullLimit(bot.id, next));
    } catch (err) {
      setError(describeError(err));
    }
  };
  return (
    <div className="info-row info-row--switch full-limit">
      <Switch checked={on} disabled={readable !== true && !on} onChange={(next) => void toggle(next)}>{FULL_LIMIT_LABEL}</Switch>
      {on ? <p className="info-row__hint">On until {zoneStamp(bot.full_limit_until)}</p> : null}
      {readable === false && !on ? <p className="info-row__hint">{FULL_LIMIT_REFUSAL}</p> : null}
      {error ? <ErrorNotice message={error} /> : null}
    </div>
  );
}
