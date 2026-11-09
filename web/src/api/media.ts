import { errorFrom } from "./client";

// A picture on a chat message (owner, 2026-11-05: pictures and video in the chat): yours, a frame of your video, or
// a screenshot the bot sent.
export interface MediaOut {
  id: string;
  width: number;
  height: number;
  source: "you" | "bot";
  group: "video" | null;
}

export interface UploadedMedia {
  id: string;
  width: number;
  height: number;
}

export const MEDIA_MAX = 8; // the server's cap per message
export const PHOTOS_MAX = 4;

export function mediaUrl(id: string): string {
  return `/api/media/${encodeURIComponent(id)}`;
}

// One picture into the chat's thread; a video's frame says so. The server's plain `detail` comes back on a refusal.
export async function uploadMedia(threadId: string, file: Blob, video: boolean): Promise<UploadedMedia> {
  const form = new FormData();
  form.append("file", file, file instanceof File ? file.name : "frame.jpg");
  if (video) form.append("video", "1");
  const response = await fetch(`/api/threads/${encodeURIComponent(threadId)}/media`, {
    method: "POST", credentials: "include", body: form,
  });
  if (!response.ok) throw await errorFrom(response);
  return (await response.json()) as UploadedMedia;
}
