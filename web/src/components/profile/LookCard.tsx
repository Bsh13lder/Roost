import { useState } from "react";
import { AvatarPicker } from "../AvatarPicker";
import { PictureButtons } from "../avatar/AvatarStudio";
import { SparkIcon } from "../icons";
import { lensbotShape } from "../robot/look";
import { RoleRow } from "./RoleRow";
import { surpriseLook } from "../robot/palette";
import { IconButton } from "../../ui/IconButton";
import { Tabs } from "../../ui/Tabs";
import type { AvatarOut } from "../../api/types";

type LookTab = "robot" | "upload";
const TABS = [{ id: "robot", label: "Robot" }, { id: "upload", label: "Upload" }] as const;

export interface LookCardProps {
  value: AvatarOut;
  job: string; // the bot's job: it suggests a role when none is set
  busy: boolean;
  onChange: (avatar: AvatarOut) => void;
  onPreview?: (avatar: AvatarOut | null) => void; // a drag across the shape tiles, shown on the hero
  onReset: () => void;
  onUpload: (file: File) => void;
  onRemovePicture: () => void;
}

// The compact card under the hero robot: Robot (the eighteen shapes, the colours, the role) and Upload
// tabs, Surprise me in the header and Reset at the right. Every pick saves at once; a drag across the
// tiles morphs the hero and saves where it is released. A Lensbot has no screen, so there is no screen row.
export function LookCard({ value, job, busy, onChange, onPreview, onReset, onUpload, onRemovePicture }: LookCardProps) {
  const [tab, setTab] = useState<LookTab>("robot");
  const surprise = () => {
    const next = surpriseLook({ shape: lensbotShape(value.shape), color: value.color });
    onChange({ ...value, shape: next.shape, color: next.color, badge: "none" });
  };
  return (
    <div className="look-card">
      <div className="look-card__head">
        <div className="look-card__tabs">
          <Tabs label="Look" tabs={TABS} value={tab} onChange={setTab}>{null}</Tabs>
        </div>
        <IconButton label="Surprise me" icon={<SparkIcon />} size="sm" disabled={busy} onClick={surprise} />
        <button type="button" className="btn btn--quiet btn--small" onClick={onReset}>Reset</button>
      </div>
      {tab === "robot" ? (
        <>
          <AvatarPicker value={value} onChange={onChange} onPreview={onPreview} compact />
          <RoleRow role={value.role} job={job} disabled={busy} onPick={(role) => onChange({ ...value, role, badge: "none" })} />
        </>
      ) : (
        <div className="look-card__upload">
          <PictureButtons hasPicture={Boolean(value.picture)} busy={busy} onUpload={onUpload} onRemove={onRemovePicture} />
          <p className="look-card__hint">A picture shows inside the robot.</p>
        </div>
      )}
    </div>
  );
}
