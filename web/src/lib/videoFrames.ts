// A video's frames for the chat (owner, 2026-11-05): the bot reads pictures, so a clip goes as evenly spaced JPEG
// frames taken here in the browser with <video> and <canvas>. No library.

export const VIDEO_FRAMES = 8;
export const VIDEO_MAX_SECONDS = 120;
const MAX_SIDE = 1280;
const JPEG_QUALITY = 0.8;
export const VIDEO_TOO_LONG = "Pick a video of 2 minutes or less.";
export const VIDEO_UNREADABLE = "Couldn't read that video.";

// The middle of each of `count` equal slices of the clip.
export function frameTimes(duration: number, count = VIDEO_FRAMES): number[] {
  if (!(duration > 0) || count <= 0) return [];
  return Array.from({ length: count }, (_, i) => (duration * (2 * i + 1)) / (2 * count));
}

function once(target: HTMLVideoElement, event: string): Promise<void> {
  return new Promise((resolve, reject) => {
    target.addEventListener(event, () => resolve(), { once: true });
    target.addEventListener("error", () => reject(new Error(VIDEO_UNREADABLE)), { once: true });
  });
}

function toJpeg(canvas: HTMLCanvasElement): Promise<Blob> {
  return new Promise((resolve, reject) => {
    canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error(VIDEO_UNREADABLE))), "image/jpeg", JPEG_QUALITY);
  });
}

export async function grabFrames(file: File, count = VIDEO_FRAMES): Promise<Blob[]> {
  const url = URL.createObjectURL(file);
  const video = document.createElement("video");
  video.muted = true;
  video.preload = "auto";
  video.src = url;
  try {
    await once(video, "loadedmetadata");
    if (video.duration > VIDEO_MAX_SECONDS) throw new Error(VIDEO_TOO_LONG);
    const scale = Math.min(1, MAX_SIDE / Math.max(video.videoWidth, video.videoHeight, 1));
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(video.videoWidth * scale);
    canvas.height = Math.round(video.videoHeight * scale);
    const context = canvas.getContext("2d");
    if (!context) throw new Error(VIDEO_UNREADABLE);
    const out: Blob[] = [];
    for (const at of frameTimes(video.duration, count)) {
      video.currentTime = at;
      await once(video, "seeked");
      context.drawImage(video, 0, 0, canvas.width, canvas.height);
      out.push(await toJpeg(canvas));
    }
    return out;
  } finally {
    URL.revokeObjectURL(url);
  }
}
