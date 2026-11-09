// SPDX-License-Identifier: MIT
// Adapted from LazyClaw web/src/pages/Sheets.tsx @ 21e1002 (Univer sheets mount, createWorkbook, SheetValueChanged /
// SheetSkeletonChanged autosave, wb.save()), for Roost
import { LocaleType, mergeLocales } from "@univerjs/core";
import type { FUniver } from "@univerjs/core/facade";
import { UniverSheetsCorePreset } from "@univerjs/preset-sheets-core";
import SheetsCoreEnUS from "@univerjs/preset-sheets-core/locales/en-US";
import "@univerjs/preset-sheets-core/lib/index.css";
import { createUniver } from "./createUniver";
import { disposeAfterCommit, mountHost, type UniverKit } from "./kit";

type WorkbookData = Parameters<FUniver["createWorkbook"]>[0];

export const sheetKit: UniverKit = {
  mount(container, payload, onChange) {
    const host = mountHost(container);
    const { univer, univerAPI } = createUniver(LocaleType.EN_US, { [LocaleType.EN_US]: mergeLocales(SheetsCoreEnUS) },
      [UniverSheetsCorePreset({ container: host })]);
    univerAPI.createWorkbook(payload as unknown as WorkbookData);
    // Cell edits fire SheetValueChanged; resizing, inserting and deleting rows fire SheetSkeletonChanged.
    const listeners = [
      univerAPI.addEvent(univerAPI.Event.SheetValueChanged, onChange),
      univerAPI.addEvent(univerAPI.Event.SheetSkeletonChanged, onChange),
    ];
    return {
      snapshot: () => (univerAPI.getActiveWorkbook()?.save() as unknown as Record<string, unknown> | undefined) ?? null,
      dispose: () => {
        listeners.forEach((listener) => listener.dispose());
        disposeAfterCommit(host, () => univer.dispose());
      },
    };
  },
};
