import { useState } from "react";
import { Avatar } from "../Avatar";
import { LookCard } from "./LookCard";
import { Popover } from "../../ui/Popover";
import { Sheet } from "../../ui/Sheet";
import { Tooltip } from "../../ui/Tooltip";
import { PencilIcon } from "../icons";
import { useMediaQuery } from "../../hooks/useMediaQuery";
import { PHONE_QUERY } from "../panel/panelTabs";
import { ErrorNotice } from "../ErrorNotice";
import { useTemplates } from "../../hooks/useTemplates";
import { DEFAULT_LENSBOT_SHAPE, lookOf } from "../robot/look";
import { BOT_DEFAULT_COLORS } from "../robot/palette";
import { PictureError, shrinkPicture } from "../../lib/picture";
import * as botsApi from "../../api/bots";
import { describeError } from "../../api/client";
import type { AvatarOut, BotOut } from "../../api/types";

const PLAIN_LOOK: AvatarOut = { shape: DEFAULT_LENSBOT_SHAPE, color: BOT_DEFAULT_COLORS[0], badge: "none" };

function useBotChange(onChange: (bot: BotOut) => void) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const run = async (change: () => Promise<BotOut>) => {
    setBusy(true);
    setError(null);
    try {
      onChange(await change());
    } catch (err) {
      setError(err instanceof PictureError ? err.message : describeError(err));
    } finally {
      setBusy(false);
    }
  };
  return { busy, error, run };
}

// The hero robot is the way in to its look: hover or focus dims it and shows a pencil; a click squishes
// it and opens the look card under it (a bottom sheet on a phone). A pick saves at once, and the hero
// shows it (and a drag's passing shapes) before the save lands; Reset goes back to the bot's template
// look (or the plain violet Mochi); Upload puts a picture inside the robot.
export function AvatarEditor({ bot, onChange, control = false }: {
  bot: BotOut; onChange: (bot: BotOut) => void; control?: boolean; // control: an open Stuck card (C3), a hand in its eye
}) {
  const { templates } = useTemplates();
  const { busy, error, run } = useBotChange(onChange);
  const [open, setOpen] = useState(false);
  const [preview, setPreview] = useState<AvatarOut | null>(null);
  const phone = useMediaQuery(PHONE_QUERY);
  const defaultLook = templates.find((t) => t.id === bot.template_id)?.avatar ?? PLAIN_LOOK;
  const shown = preview ?? bot.avatar;
  const save = async (avatar: AvatarOut) => {
    setPreview(avatar);
    await run(() => botsApi.updateBot(bot.id, { avatar: lookOf(avatar) }));
    setPreview(null);
  };
  const upload = (file: File) => run(async () => botsApi.uploadPicture(bot.id, await shrinkPicture(file)));
  const trigger = (
    <button type="button" className="look-trigger" aria-label="Edit look" aria-haspopup="dialog" aria-expanded={open}
      onClick={phone ? () => setOpen(true) : undefined}>
      <Avatar avatar={shown} status={bot.status} activity={bot.activity} size={96} label={false} decorative star={bot.is_primary}
        botId={bot.id} poke control={control} />
      <span className="look-trigger__pencil" aria-hidden="true"><PencilIcon /></span>
    </button>
  );
  const card = (
    <>
      <LookCard value={shown} job={bot.job} busy={busy} onChange={(avatar) => void save(avatar)} onPreview={setPreview}
        onReset={() => void save(defaultLook)}
        onUpload={(file) => void upload(file)} onRemovePicture={() => void run(() => botsApi.removePicture(bot.id))} />
      {error ? <ErrorNotice message={error} /> : null}
    </>
  );
  return (
    <div className="look-edit">
      {phone ? (
        <>
          <Tooltip content="Edit look">{trigger}</Tooltip>
          <Sheet open={open} onOpenChange={setOpen} title="Edit look" size="bottom">{card}</Sheet>
        </>
      ) : (
        <Tooltip content="Edit look">
          <span className="look-edit__anchor">
            <Popover trigger={trigger} label="Edit look" open={open} onOpenChange={setOpen} side="bottom" align="center">{card}</Popover>
          </span>
        </Tooltip>
      )}
    </div>
  );
}
