import type { DeskStatusOut } from "../api/types";

export interface ComputerPanelProps {
  status: DeskStatusOut | null;
  onStartBrowser: () => Promise<void>;
  onStopBrowser: () => Promise<void>;
}

// The Computer tab's window controls. There is no command box: a bot's computer is watched and, when
// you choose, taken over with Take control.
export function ComputerPanel({ status, onStartBrowser, onStopBrowser }: ComputerPanelProps) {
  const browser = status ? status.browser : "unknown";
  return (
    <div className="computer-panel">
      <section className="computer-card" aria-labelledby="computer-window-title">
        <div className="computer-card__head">
          <h2 id="computer-window-title" className="computer-card__title">
            Window
          </h2>
          <span className={`state-pill state-pill--${browser}`}>
            <span className="state-pill__dot" aria-hidden="true" />
            <span className="state-pill__text">{browser}</span>
          </span>
        </div>
        <p className="computer-card__lede">This bot&rsquo;s own Brave window on your Mac, kept apart from yours.</p>
        <div className="computer-card__actions">
          <button type="button" className="btn btn--primary" onClick={() => void onStartBrowser()}>
            Open window
          </button>
          <button type="button" className="btn btn--quiet" onClick={() => void onStopBrowser()}>
            Close window
          </button>
        </div>
      </section>
    </div>
  );
}
