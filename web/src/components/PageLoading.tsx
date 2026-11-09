// What a lazy page shows while its chunk arrives (lead task 03): one quiet line, read once by a screen reader.
export function PageLoading() {
  return <p className="page-loading" role="status" aria-live="polite">Loading&hellip;</p>;
}
