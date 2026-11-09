import { useEffect, useState } from "react";
import { mediaUrl, type MediaOut } from "../../api/media";

export function videoLabel(frames: number): string {
  return `Video · ${frames} frames`;
}

interface Group {
  readonly video: boolean;
  readonly items: readonly MediaOut[];
}

// Photos one by one, a video's frames as one run, in the message's order.
export function mediaGroups(media: readonly MediaOut[]): Group[] {
  const groups: { video: boolean; items: MediaOut[] }[] = [];
  for (const item of media) {
    const video = item.group === "video";
    const last = groups[groups.length - 1];
    if (last && last.video === video) last.items.push(item);
    else groups.push({ video, items: [item] });
  }
  return groups;
}

// A message's pictures: photos in a small grid, a video's frames as one strip marked ▶ "Video · 8 frames". They load
// lazily from the gateway with your session; a click opens them full size.
export function MessageMedia({ media }: { media: readonly MediaOut[] }) {
  const [open, setOpen] = useState<number | null>(null);
  if (media.length === 0) return null;
  let index = 0;
  return (
    <div className="message-media">
      {mediaGroups(media).map((group) => {
        const start = index;
        index += group.items.length;
        return group.video ? (
          <button key={group.items[0].id} type="button" className="message-media__video" aria-label="Open the video"
            onClick={() => setOpen(start)}>
            <span className="message-media__strip">
              {group.items.map((item) => (
                <img key={item.id} className="message-media__frame" src={mediaUrl(item.id)} alt="" loading="lazy" />
              ))}
            </span>
            <span className="message-media__label"><span aria-hidden="true">▶ </span>{videoLabel(group.items.length)}</span>
          </button>
        ) : (
          <div key={group.items[0].id} className="message-media__grid">
            {group.items.map((item, at) => (
              <button key={item.id} type="button" className="message-media__open" aria-label={`Open picture ${start + at + 1}`}
                onClick={() => setOpen(start + at)}>
                <img className="message-media__thumb" src={mediaUrl(item.id)} alt={`Picture ${start + at + 1}`} loading="lazy" />
              </button>
            ))}
          </div>
        );
      })}
      {open === null ? null : <MediaViewer media={media} start={open} onClose={() => setOpen(null)} />}
    </div>
  );
}

// Full size, one at a time: ← → or the buttons move, Escape or × closes.
function MediaViewer({ media, start, onClose }: { media: readonly MediaOut[]; start: number; onClose: () => void }) {
  const [at, setAt] = useState(start);
  const step = (by: number) => setAt((now) => (now + by + media.length) % media.length);
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
      else if (event.key === "ArrowRight") step(1);
      else if (event.key === "ArrowLeft") step(-1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });
  const item = media[at];
  return (
    <div className="media-viewer" role="dialog" aria-modal="true" aria-label="Pictures">
      <button type="button" className="media-viewer__close" onClick={onClose} aria-label="Close">×</button>
      {media.length > 1 ? <button type="button" className="media-viewer__step" onClick={() => step(-1)} aria-label="Previous picture">‹</button> : null}
      <img className="media-viewer__picture" src={mediaUrl(item.id)} alt={`Picture ${at + 1} of ${media.length}`} />
      {media.length > 1 ? <button type="button" className="media-viewer__step" onClick={() => step(1)} aria-label="Next picture">›</button> : null}
    </div>
  );
}
