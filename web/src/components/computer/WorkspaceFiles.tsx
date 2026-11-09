import { useState, type ReactNode } from "react";
import { ErrorNotice } from "../ErrorNotice";
import { Button } from "../../ui/Button";
import { describeError } from "../../api/client";
import { listWorkspaceFiles, wipeWorkspace, type WorkspaceEntry, type WorkspaceListing } from "../../api/workspace";
import { WIPE_LABEL, WIPED_TEXT, wipeConfirmText, wipeForGoodLabel } from "./constants";

const parentOf = (path: string) => path.split("/").slice(0, -1).join("/");
const joined = (path: string, name: string) => (path ? `${path}/${name}` : name);
const EMPTY_LISTING: WorkspaceListing = { path: "", entries: [], more: false };

function EntryRow({ entry, onOpen }: { entry: WorkspaceEntry; onOpen: () => void }) {
  if (entry.kind === "dir") {
    return (
      <li className="site-logins__row">
        <button type="button" className="link-btn" onClick={onOpen}>{`${entry.name}/`}</button>
      </li>
    );
  }
  const size = entry.kind === "file" && entry.size !== null ? ` · ${entry.size} bytes` : ` · ${entry.kind}`;
  return <li className="site-logins__row"><span className="site-logins__label">{`${entry.name}${size}`}</span></li>;
}

function ListingView({ listing, busy, load }: { listing: WorkspaceListing; busy: boolean; load: (path: string) => void }) {
  return (
    <>
      <p className="site-logins__empty">{listing.path ? `/workspace/${listing.path}` : "/workspace"}</p>
      {listing.path ? (
        <Button variant="ghost" size="sm" disabled={busy} onClick={() => load(parentOf(listing.path))}>Up</Button>
      ) : null}
      {listing.entries.length === 0 ? <p className="site-logins__empty">No files yet.</p> : null}
      <ul className="site-logins__list">
        {listing.entries.map((entry) => (
          <EntryRow key={entry.name} entry={entry} onOpen={() => load(joined(listing.path, entry.name))} />
        ))}
      </ul>
      {listing.more ? <p className="site-logins__empty">More files are not shown.</p> : null}
    </>
  );
}

// Wipe workspace: a confirm that names the bot, then one call; the server also clears the workspace's
// "from web content" mark, so the bot's next run starts clean.
function WipeControl({ botName, busy, onWipe }: { botName: string; busy: boolean; onWipe: () => void }) {
  const [confirming, setConfirming] = useState(false);
  if (!confirming) {
    return <Button variant="ghost" size="sm" disabled={busy} onClick={() => setConfirming(true)}>{WIPE_LABEL}</Button>;
  }
  return (
    <div className="project-actions__confirm" role="group" aria-label={WIPE_LABEL}>
      <p>{wipeConfirmText(botName)}</p>
      <Button variant="danger" size="sm" aria-label={wipeForGoodLabel(botName)} disabled={busy}
        onClick={() => { setConfirming(false); onWipe(); }}>{WIPE_LABEL}</Button>
      <Button variant="ghost" size="sm" onClick={() => setConfirming(false)}>Cancel</Button>
    </div>
  );
}

// Programs: the files in the bot's own workspace, read-only, and Wipe workspace. Nothing loads until you ask, so
// opening the tab never wakes the workspace.
// `children`: settings of the workspace shown under the title (Internet in the workspace).
export function WorkspaceFiles({ botId, botName, children }: { botId: string; botName: string; children?: ReactNode }) {
  const [listing, setListing] = useState<WorkspaceListing | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const attempt = async (work: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    setNote(null);
    try {
      await work();
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusy(false);
    }
  };
  const load = (path: string) => void attempt(async () => setListing(await listWorkspaceFiles(botId, path)));
  const wipe = () => void attempt(async () => {
    await wipeWorkspace(botId);
    setListing(EMPTY_LISTING);
    setNote(WIPED_TEXT);
  });
  return (
    <section className="site-logins" aria-labelledby="workspace-files-title">
      <h2 id="workspace-files-title" className="site-logins__title">Workspace files</h2>
      {children}
      {listing === null ? (
        <Button variant="ghost" size="sm" disabled={busy} onClick={() => load("")}>Show files</Button>
      ) : (
        <ListingView listing={listing} busy={busy} load={load} />
      )}
      <WipeControl botName={botName} busy={busy} onWipe={wipe} />
      {note ? <p className="site-logins__empty" role="status">{note}</p> : null}
      {error ? <ErrorNotice message={error} /> : null}
    </section>
  );
}
