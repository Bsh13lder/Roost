import { apiRequest } from "./client";
import type { CommentOut } from "./types";

// Comments on the user's tasks (redesign P3). Bots comment through their tools; here the user reads
// the thread and writes, edits or deletes their own (the gateway refuses a bot's comment with 403).

export interface CommentIn {
  body: string;
  step_id?: string; // one of the task's steps; none is the whole task
}

const threadPath = (taskId: string) => `/api/tasks/${encodeURIComponent(taskId)}/comments`;
const commentPath = (commentId: string) => `/api/comments/${encodeURIComponent(commentId)}`;

export function listComments(taskId: string): Promise<CommentOut[]> {
  return apiRequest<CommentOut[]>("GET", threadPath(taskId));
}

export function addComment(taskId: string, input: CommentIn): Promise<CommentOut> {
  return apiRequest<CommentOut>("POST", threadPath(taskId), input);
}

export function editComment(commentId: string, body: string): Promise<CommentOut> {
  return apiRequest<CommentOut>("PATCH", commentPath(commentId), { body });
}

export function deleteComment(commentId: string): Promise<void> {
  return apiRequest<void>("DELETE", commentPath(commentId));
}
