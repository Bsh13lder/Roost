import { useEffect, useRef, useState } from "react";
import { describeError } from "../../api/client";
import { listJournalDays, readJournalDay, type JournalDayOut, type JournalDaySummary } from "../../api/journal";
import { Button } from "../../ui/Button";
import { RichText } from "../chat/RichText";
import { ErrorNotice } from "../ErrorNotice";

// The note's body without its front matter: the tags and the day are already on screen.
export function journalBody(content: string): string {
  const match = /^---\n[\s\S]*?\n---\n/.exec(content);
  return match ? content.slice(match[0].length) : content;
}

const entriesLabel = (n: number) => (n === 1 ? "1 entry" : `${n} entries`);

// "Journal" on the Info tab (obsidian track): the bot's recent days; a day opens read-only as Markdown.
// A lazy chunk, loaded when the fold opens.
export default function JournalSection({ botId }: { botId: string }) {
  const [days, setDays] = useState<readonly JournalDaySummary[] | null>(null);
  const [open, setOpen] = useState<JournalDayOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const latest = useRef(0); // a slower, older load never wins
  useEffect(() => {
    let live = true;
    listJournalDays(botId)
      .then((loaded) => { if (live) { setDays(loaded); setError(null); } })
      .catch((err: unknown) => { if (live) setError(describeError(err)); });
    return () => { live = false; };
  }, [botId]);
  const show = (day: string) => {
    const ticket = ++latest.current;
    readJournalDay(botId, day)
      .then((loaded) => { if (ticket === latest.current) { setOpen(loaded); setError(null); } })
      .catch((err: unknown) => { if (ticket === latest.current) setError(describeError(err)); });
  };
  if (open) {
    return (
      <section className="info-card journal" aria-label={`Journal for ${open.day}`}>
        <div className="journal__head">
          <h3 className="journal__title">{open.day}</h3>
          <Button size="sm" variant="secondary" onClick={() => setOpen(null)}>All days</Button>
        </div>
        {open.tainted ? <p className="journal__note">Some entries came after reading web content.</p> : null}
        <div className="journal__body"><RichText text={journalBody(open.content)} id={`journal-${open.day}`} /></div>
        {error ? <ErrorNotice message={error} /> : null}
      </section>
    );
  }
  return (
    <section className="info-card journal" aria-label="Journal">
      {days === null && !error ? <p className="journal__note">Loading the journal&hellip;</p> : null}
      {days !== null && days.length === 0 ? <p className="journal__note">Nothing in the journal yet.</p> : null}
      {days && days.length > 0 ? (
        <ul className="journal__days">
          {days.map((d) => (
            <li key={d.day}>
              <button type="button" className="journal__day" onClick={() => show(d.day)}>
                <span>{d.day}</span>
                <span className="journal__note">{entriesLabel(d.entries)}</span>
              </button>
            </li>
          ))}
        </ul>
      ) : null}
      {error ? <ErrorNotice message={error} /> : null}
    </section>
  );
}
