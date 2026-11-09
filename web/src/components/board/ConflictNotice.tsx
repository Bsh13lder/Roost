export interface ConflictNoticeProps {
  what: "note" | "document";
  onLoad: () => void;
  onKeep: () => void;
}

// A save met a newer copy: a bot or another window changed it (M2 D4). The user
// picks — see the latest, or save theirs over it. Never a silent overwrite.
export function ConflictNotice({ what, onLoad, onKeep }: ConflictNoticeProps) {
  return (
    <div className="conflict-notice" role="status">
      <p>This {what} changed somewhere else (a bot or another window) while you were editing.</p>
      <button type="button" className="btn btn--quiet btn--small" onClick={onLoad}>Load the latest</button>
      <button type="button" className="btn btn--primary btn--small" onClick={onKeep}>Keep mine</button>
    </div>
  );
}
