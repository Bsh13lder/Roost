import { useId, useRef, useState, type ChangeEvent } from "react";
import { PlusIcon } from "../icons";
import { Menu, MenuItem } from "../../ui/Menu";
import * as documentsApi from "../../api/documents";
import { describeError } from "../../api/client";
import { SavePasswordSheet } from "../vault/SavePasswordSheet";
import { SAVE_PASSWORD_MENU_ITEM } from "../vault/constants";

export const PDF_TYPE = "application/pdf";

export const PICTURE_ACCEPT = "image/jpeg,image/png,image/webp";

// The composer's + (restructure slice 3): pictures and a video for the bot to look at (owner, 2026-11-05; they wait
// above the composer until Send), Choose file, a PDF into your documents (its title is handed back), and Save a
// password (Vault: passwords, 2026-11-08): a sheet that posts to the Vault only, never to the chat.
export function ComposerPlus({ onAdded, onError, onPictures, onVideo }: {
  onAdded: (title: string) => void; onError: (message: string) => void;
  onPictures?: (files: File[]) => void; onVideo?: (file: File) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const picturesRef = useRef<HTMLInputElement>(null);
  const videoRef = useRef<HTMLInputElement>(null);
  const inputId = useId();
  const [savingPassword, setSavingPassword] = useState(false);
  const onPickPictures = (event: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files ?? []);
    event.target.value = "";
    if (files.length > 0) onPictures?.(files);
  };
  const onPickVideo = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (file) onVideo?.(file);
  };
  const onPick = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = ""; // the same file can be picked again
    if (!file) return;
    if (file.type !== PDF_TYPE) {
      onError("Roost can add a PDF here. Other files come later.");
      return;
    }
    try {
      onAdded((await documentsApi.uploadPdf(file)).title);
    } catch (err) {
      onError(describeError(err));
    }
  };
  return (
    <>
      <Menu label="Add to the chat" side="top" align="start" trigger={<PlusIcon />}>
        {onPictures ? <MenuItem onSelect={() => picturesRef.current?.click()}>Attach pictures</MenuItem> : null}
        {onVideo ? <MenuItem onSelect={() => videoRef.current?.click()}>Attach a video</MenuItem> : null}
        <MenuItem onSelect={() => inputRef.current?.click()}>Choose file</MenuItem>
        <MenuItem onSelect={() => setSavingPassword(true)}>{SAVE_PASSWORD_MENU_ITEM}</MenuItem>
      </Menu>
      <SavePasswordSheet open={savingPassword} onOpenChange={setSavingPassword} />
      {onPictures ? (
        <input ref={picturesRef} type="file" accept={PICTURE_ACCEPT} multiple className="composer-plus__input"
          aria-label="Attach pictures" onChange={onPickPictures} />
      ) : null}
      {onVideo ? (
        <input ref={videoRef} type="file" accept="video/*" className="composer-plus__input"
          aria-label="Attach a video" onChange={onPickVideo} />
      ) : null}
      <input ref={inputRef} id={inputId} type="file" accept={PDF_TYPE} className="composer-plus__input"
        aria-label="Choose a PDF" onChange={(event) => void onPick(event)} />
    </>
  );
}
