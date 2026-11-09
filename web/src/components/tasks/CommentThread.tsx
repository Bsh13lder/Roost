import { useCallback, useEffect, useState, type KeyboardEvent } from "react";
import { ErrorNotice } from "../ErrorNotice";
import { COMMENT_ROWS, MAX_COMMENT } from "./constants";
import { authorName, momentText } from "./authors";
import { useLiveState } from "../../hooks/useLiveStore";
import * as commentsApi from "../../api/comments";
import { describeError } from "../../api/client";
import type { CommentOut, TaskOut } from "../../api/types";
import { Badge } from "../../ui/Badge";
import { Button } from "../../ui/Button";
import { Select, type SelectOption } from "../../ui/Select";
import { Textarea } from "../../ui/Textarea";

const WHOLE_TASK = "task"; // a Select option is never "" (ui/Select.tsx)

// The thread, oldest first; it reloads on tasks_changed, which a comment from anywhere publishes.
function useThread(taskId: string) {
  const version = useLiveState().boardVersion.tasks;
  const [comments, setComments] = useState<readonly CommentOut[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => {
    commentsApi.listComments(taskId)
      .then((found) => { setComments(found); setError(null); })
      .catch((err: unknown) => setError(describeError(err)));
  }, [taskId]);
  useEffect(() => load(), [load, version]);
  return { comments, error, setError, load };
}

// Cmd/Ctrl+Enter sends; Enter alone is a new line.
const sendKey = (event: KeyboardEvent) => event.key === "Enter" && (event.metaKey || event.ctrlKey);

interface CommentItemProps {
  comment: CommentOut;
  task: TaskOut;
  onChanged: () => void;
  onError: (message: string) => void;
}

function CommentItem({ comment, task, onChanged, onError }: CommentItemProps) {
  const { bots } = useLiveState();
  const [editing, setEditing] = useState<string | null>(null);
  const step = task.steps.find((s) => s.id === comment.step_id);
  const act = (request: Promise<unknown>) => {
    request.then(() => { setEditing(null); onChanged(); }).catch((err: unknown) => onError(describeError(err)));
  };
  const author = authorName(comment.author, bots);
  return (
    <li className="comment">
      <div className="comment__head">
        <span className="comment__author">{author}</span>
        {step ? <span className="comment__step">on “{step.title}”</span> : null}
        <time className="comment__time" dateTime={comment.created_at}>{momentText(comment.created_at)}</time>
        {comment.edited_at ? <span className="comment__edited">edited</span> : null}
        {comment.tainted ? <Badge tone="danger">from web content</Badge> : null}
      </div>
      {editing === null ? <p className="comment__body">{comment.body}</p> : (
        <div className="comment__edit">
          <Textarea aria-label="Edit your comment" value={editing} maxLength={MAX_COMMENT} maxRows={COMMENT_ROWS}
            onChange={(e) => setEditing(e.target.value)} />
          <Button size="sm" variant="primary" disabled={!editing.trim()}
            onClick={() => act(commentsApi.editComment(comment.id, editing))}>Save</Button>
          <Button size="sm" variant="ghost" onClick={() => setEditing(null)}>Cancel</Button>
        </div>
      )}
      {comment.author === "user" && editing === null ? (
        <div className="comment__actions">
          <Button size="sm" variant="ghost" onClick={() => setEditing(comment.body)}>Edit</Button>
          <Button size="sm" variant="ghost" onClick={() => act(commentsApi.deleteComment(comment.id))}>Delete</Button>
        </div>
      ) : null}
    </li>
  );
}

function Composer({ task, onSent }: { task: TaskOut; onSent: () => void }) {
  const [body, setBody] = useState("");
  const [about, setAbout] = useState(WHOLE_TASK);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const options: ReadonlyArray<SelectOption> = [
    { value: WHOLE_TASK, label: "The whole task" }, ...task.steps.map((step) => ({ value: step.id, label: step.title })),
  ];
  const send = async () => {
    if (!body.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      await commentsApi.addComment(task.id, about === WHOLE_TASK ? { body } : { body, step_id: about });
      setBody("");
      onSent();
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusy(false);
    }
  };
  return (
    <form className="comment-composer" onSubmit={(e) => { e.preventDefault(); void send(); }}>
      <Textarea aria-label="New comment" placeholder="Write a comment…" value={body} maxLength={MAX_COMMENT}
        maxRows={COMMENT_ROWS} onChange={(e) => setBody(e.target.value)}
        onKeyDown={(e) => { if (sendKey(e)) { e.preventDefault(); void send(); } }} />
      <div className="comment-composer__row">
        {task.steps.length > 0 ? <Select label="About" value={about} options={options} onChange={setAbout} size="md" /> : null}
        <Button type="submit" size="md" variant="primary" disabled={busy || !body.trim()}>Comment</Button>
      </div>
      {error ? <ErrorNotice message={error} /> : null}
    </form>
  );
}

// The drawer's Comments (redesign P3): the user's and the bots' comments on the task or a step, plain
// text only, a web-made one marked; the user edits or deletes only their own.
export function CommentThread({ task }: { task: TaskOut }) {
  const { comments, error, setError, load } = useThread(task.id);
  return (
    <section className="task-drawer__section" aria-label="Comments">
      <h3 className="task-drawer__heading">Comments</h3>
      {error ? <ErrorNotice message={error} onRetry={load} /> : null}
      {comments !== null && comments.length === 0 ? <p className="comment-empty">No comments yet.</p> : null}
      {comments && comments.length > 0 ? (
        <ul className="comment-list">
          {comments.map((comment) => (
            <CommentItem key={comment.id} comment={comment} task={task} onChanged={load} onError={setError} />
          ))}
        </ul>
      ) : null}
      <Composer task={task} onSent={load} />
    </section>
  );
}
