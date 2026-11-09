// SPDX-License-Identifier: MIT
// Adapted from LazyClaw web/src/pages/Docs.tsx @ 21e1002 (Univer docs mount, createUniverDoc, CommandExecuted autosave), for Roost
import { LocaleType, mergeLocales } from "@univerjs/core";
import type { FUniver } from "@univerjs/core/facade";
import { UniverDocsCorePreset } from "@univerjs/preset-docs-core";
import DocsCoreEnUS from "@univerjs/preset-docs-core/locales/en-US";
import "@univerjs/preset-docs-core/lib/index.css";
import { createUniver } from "./createUniver";
import { disposeAfterCommit, mountHost, type UniverKit } from "./kit";

type DocData = Parameters<FUniver["createUniverDoc"]>[0];

export const docKit: UniverKit = {
  mount(container, payload, onChange) {
    const host = mountHost(container);
    const { univer, univerAPI } = createUniver(LocaleType.EN_US, { [LocaleType.EN_US]: mergeLocales(DocsCoreEnUS) },
      [UniverDocsCorePreset({ container: host })]);
    univerAPI.createUniverDoc(payload as unknown as DocData);
    // The docs facade has no DocChanged event: CommandExecuted fires on every edit (LazyClaw's note).
    const listener = univerAPI.addEvent(univerAPI.Event.CommandExecuted, onChange);
    return {
      snapshot: () => (univerAPI.getActiveDocument()?.getSnapshot() as unknown as Record<string, unknown> | undefined) ?? null,
      dispose: () => { listener.dispose(); disposeAfterCommit(host, () => univer.dispose()); },
    };
  },
};
