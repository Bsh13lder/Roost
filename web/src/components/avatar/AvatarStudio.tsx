import { Avatar } from "../Avatar";
import { AvatarPicker } from "../AvatarPicker";
import { SparkIcon, UploadIcon } from "../icons";
import { lensbotShape } from "../robot/look";
import { surpriseLook } from "../robot/palette";
import { Button } from "../../ui/Button";
import { PICTURE_ACCEPT } from "../../lib/picture";
import type { AvatarOut, BotStatus } from "../../api/types";

export interface AvatarStudioProps {
  value: AvatarOut; // the look shown, with its picture when it has one
  onChange: (avatar: AvatarOut) => void;
  status?: BotStatus; // the preview shows this status (the bot's own on its profile)
  star?: boolean;
  preview?: boolean; // the big live preview (the New bot form has its own)
  onUpload?: (file: File) => void; // given: Upload a picture (the bot must exist first)
  onRemovePicture?: () => void; // given, with a picture: Remove picture
  busy?: boolean;
}

export function PictureButtons({ hasPicture, busy, onUpload, onRemove }: {
  hasPicture: boolean; busy: boolean; onUpload: (file: File) => void; onRemove?: () => void;
}) {
  return (
    <>
      <label className="btn btn--secondary btn--sm avatar-studio__upload" aria-disabled={busy || undefined}>
        <UploadIcon /> Upload a picture
        <input type="file" accept={PICTURE_ACCEPT} className="sr-only" aria-label="Upload a picture" disabled={busy}
          onChange={(event) => { const file = event.target.files?.[0]; event.target.value = ""; if (file) onUpload(file); }} />
      </label>
      {hasPicture && onRemove ? <Button variant="ghost" size="sm" disabled={busy} onClick={onRemove}>Remove picture</Button> : null}
    </>
  );
}

// The avatar editor (redesign P1, Lensbots since avatars v7): a big live preview showing the bot's status,
// its shape and colour, Surprise me, and a picture of its own inside the robot.
export function AvatarStudio({
  value, onChange, status = "resting", star = false, preview = true, onUpload, onRemovePicture, busy = false,
}: AvatarStudioProps) {
  const surprise = () => {
    const next = surpriseLook({ shape: lensbotShape(value.shape), color: value.color });
    onChange({ ...value, shape: next.shape, color: next.color, badge: "none" });
  };
  return (
    <div className="avatar-studio">
      {preview ? (
        <div className="avatar-studio__preview" aria-label="Preview" role="group">
          <Avatar avatar={value} status={status} star={star} size={160} />
        </div>
      ) : null}
      <div className="avatar-studio__controls">
        <AvatarPicker value={value} onChange={onChange} />
        <div className="avatar-studio__actions">
          <Button size="sm" disabled={busy} onClick={surprise}><SparkIcon /> Surprise me</Button>
          {onUpload ? (
            <PictureButtons hasPicture={Boolean(value.picture)} busy={busy} onUpload={onUpload} onRemove={onRemovePicture} />
          ) : null}
        </div>
      </div>
    </div>
  );
}
