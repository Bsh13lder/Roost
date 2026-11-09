import { useCallback, useEffect, useRef, useState } from "react";
import { MEDIA_MAX, PHOTOS_MAX, uploadMedia, type MediaOut } from "../../api/media";
import { describeError } from "../../api/client";
import { grabFrames, VIDEO_UNREADABLE } from "../../lib/videoFrames";

// One picture waiting above the composer: a photo or a video's frame; `uploaded` once the server took it, so a
// retry skips it.
export interface TrayItem {
  readonly key: number;
  readonly blob: Blob;
  readonly url: string;
  readonly video: boolean;
  readonly uploaded?: MediaOut;
}

export const TOO_MANY_PHOTOS = `Up to ${PHOTOS_MAX} pictures at a time.`;
export const VIDEO_TAKES_ALL = `A video takes all ${MEDIA_MAX} picture places. Remove the pictures first.`;
const NOT_A_PICTURE = "Roost takes JPEG, PNG or WebP pictures.";
const PICTURE_TYPES = ["image/jpeg", "image/png", "image/webp"];

export interface MediaTray {
  readonly items: readonly TrayItem[];
  readonly busy: boolean;
  readonly done: number;
  readonly error: string | null;
  addPictures: (files: readonly File[]) => void;
  addVideo: (file: File) => Promise<void>;
  remove: (key: number) => void;
  upload: (threadId: string) => Promise<MediaOut[] | null>;
  clear: () => void;
}

function objectUrl(blob: Blob): string {
  return typeof URL.createObjectURL === "function" ? URL.createObjectURL(blob) : "";
}

function release(items: readonly TrayItem[]): void {
  if (typeof URL.revokeObjectURL !== "function") return;
  items.forEach((item) => { if (item.url) URL.revokeObjectURL(item.url); });
}

export function useMediaTray(): MediaTray {
  const [items, setItems] = useState<readonly TrayItem[]>([]);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const nextKey = useRef(0);
  const current = useRef(items);
  current.current = items;
  useEffect(() => () => release(current.current), []);

  const make = (blob: Blob, video: boolean): TrayItem => ({ key: nextKey.current++, blob, url: objectUrl(blob), video });

  const addPictures = useCallback((files: readonly File[]) => {
    const now = current.current;
    if (files.some((file) => !PICTURE_TYPES.includes(file.type))) { setError(NOT_A_PICTURE); return; }
    if (now.some((item) => item.video)) { setError(VIDEO_TAKES_ALL); return; }
    if (now.length + files.length > PHOTOS_MAX) { setError(TOO_MANY_PHOTOS); return; }
    setError(null);
    setItems([...now, ...files.map((file) => make(file, false))]);
  }, []);

  const addVideo = useCallback(async (file: File) => {
    if (current.current.length > 0) { setError(VIDEO_TAKES_ALL); return; }
    try {
      const frames = await grabFrames(file);
      if (frames.length === 0) throw new Error(VIDEO_UNREADABLE);
      setError(null);
      setItems(frames.slice(0, MEDIA_MAX).map((frame) => make(frame, true)));
    } catch (err) {
      setError(err instanceof Error ? err.message : VIDEO_UNREADABLE);
    }
  }, []);

  // A picture goes alone; a video's frames all go together.
  const remove = useCallback((key: number) => {
    const now = current.current;
    const gone = now.find((item) => item.key === key);
    const kept = now.filter((item) => item.key !== key && !(gone?.video && item.video));
    release(now.filter((item) => !kept.includes(item)));
    setError(null);
    setItems(kept);
  }, []);

  // Every picture not yet taken, in order; null (with the reason in `error`) when one fails.
  const upload = useCallback(async (threadId: string): Promise<MediaOut[] | null> => {
    setBusy(true);
    setDone(0);
    setError(null);
    let list = current.current;
    const taken: MediaOut[] = [];
    try {
      for (const item of list) {
        const media = item.uploaded ?? { ...(await uploadMedia(threadId, item.blob, item.video)),
          source: "you" as const, group: item.video ? "video" as const : null };
        taken.push(media);
        list = list.map((each) => (each.key === item.key ? { ...each, uploaded: media } : each));
        setItems(list);
        setDone(taken.length);
      }
      return taken;
    } catch (err) {
      setError(describeError(err));
      return null;
    } finally {
      setBusy(false);
    }
  }, []);

  const clear = useCallback(() => {
    release(current.current);
    setItems([]);
    setError(null);
    setDone(0);
  }, []);

  return { items, busy, done, error, addPictures, addVideo, remove, upload, clear };
}
