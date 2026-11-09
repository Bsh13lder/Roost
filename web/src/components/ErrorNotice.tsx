export interface ErrorNoticeProps {
  message: string;
  onRetry?: () => void;
}

// Shared "something went wrong" banner. Every page that fetches data on
// mount (Layout, Talk, Desk) renders one of these instead of being
// stuck on "Loading…" forever when that fetch rejects (project rule:
// never silently swallow errors, user-friendly messages in UI-facing
// code).
export function ErrorNotice({ message, onRetry }: ErrorNoticeProps) {
  return (
    <div className="error-notice" role="alert">
      <p className="error-notice__message">{message}</p>
      {onRetry ? (
        <button type="button" className="error-notice__retry" onClick={onRetry}>
          Retry
        </button>
      ) : null}
    </div>
  );
}
