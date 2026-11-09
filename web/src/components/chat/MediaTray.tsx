import { videoLabel } from "./MessageMedia";
import type { MediaTray as Tray } from "./useMediaTray";

// The pictures waiting above the composer, each with its ×; a video is one tile. While a Send uploads it shows how
// far it got; a failure shows why, and Send again retries.
export function MediaTray({ tray }: { tray: Tray }) {
  const { items, busy, done, error } = tray;
  if (items.length === 0 && !error) return null;
  const video = items.some((item) => item.video);
  const shown = video ? items.slice(0, 1) : items;
  return (
    <div className="media-tray">
      {shown.length > 0 ? (
        <ul className="media-tray__list">
          {shown.map((item, index) => (
            <li key={item.key} className={video ? "media-tray__item media-tray__item--video" : "media-tray__item"}>
              <img className="media-tray__thumb" src={item.url} alt={video ? "Video to send" : `Picture ${index + 1} to send`} />
              {video ? <span className="media-tray__label"><span aria-hidden="true">▶ </span>{videoLabel(items.length)}</span> : null}
              {busy ? null : (
                <button type="button" className="media-tray__remove" onClick={() => tray.remove(item.key)}
                  aria-label={video ? "Remove the video" : `Remove picture ${index + 1}`}>×</button>
              )}
            </li>
          ))}
        </ul>
      ) : null}
      {busy ? <p className="media-tray__note" role="status">Sending pictures… {done} of {items.length}</p> : null}
      {error ? <p className="media-tray__error" role="alert">{error}</p> : null}
    </div>
  );
}
