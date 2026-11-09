import { useEffect, useRef, useState } from "react";
import { ErrorNotice } from "./ErrorNotice";
import * as templatesApi from "../api/templates";
import { describeError } from "../api/client";
import type { BotOut } from "../api/types";
import { characterCount } from "../lib/botFields";
import { LENSBOT_SHAPE_LABELS, lensbotShape } from "./robot/look";
import { ROBOT_COLORS } from "./robot/palette";

// "Mochi robot, violet".
const lookInWords = ({ shape, color }: BotOut["avatar"]) => {
  const colorName = ROBOT_COLORS.find(([hex]) => hex === color.toLowerCase())?.[1] ?? color;
  return `${LENSBOT_SHAPE_LABELS[lensbotShape(shape)]} robot, ${colorName.toLowerCase()}`;
};

function saveFile(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

function useEscape(onClose: () => void) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);
}

// S1.7: the file holds name, job, instructions and look, and nothing else.
// Save file is the decision; the server refuses a field that looks like a secret.
export function ShareTemplateDialog({ bot, onClose }: { bot: BotOut; onClose: () => void }) {
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const dialog = useRef<HTMLDivElement>(null);
  useEscape(onClose);
  useEffect(() => dialog.current?.focus(), []);
  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      const file = await templatesApi.downloadTemplate(bot.id);
      saveFile(file.blob, file.filename);
      setSaved(file.filename);
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <div className="sheet-backdrop" aria-hidden="true" onClick={onClose} />
      <div className="sheet share-sheet" role="dialog" aria-modal="true" aria-label="Share as Template" tabIndex={-1} ref={dialog}>
        <header className="sheet__head">
          <h2 className="sheet__title">Share {bot.name} as a template</h2>
        </header>
        <div className="share-sheet__body">
          <p>The file holds exactly:</p>
          <ul className="share-sheet__list">
            <li>Name: {bot.name}</li>
            <li>Job: {bot.job}</li>
            <li>Instructions ({characterCount(bot.instructions)} characters)</li>
            <li>Look: {lookInWords(bot.avatar)}</li>
          </ul>
          <p className="share-sheet__never">It never holds chats, your tasks, money, notes or documents, logins, its computer or model choices.</p>
          {error ? <ErrorNotice message={error} /> : null}
          {saved ? <p className="share-sheet__saved" role="status">Saved {saved}.</p> : null}
        </div>
        <div className="sheet__actions">
          <button type="button" className="btn btn--quiet" onClick={onClose}>Close</button>
          <button type="button" className="btn btn--primary" onClick={() => void save()} disabled={busy}>Save file</button>
        </div>
      </div>
    </>
  );
}
