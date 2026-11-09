// SPDX-License-Identifier: Apache-2.0
// Adapted from @univerjs/presets 0.24.0 lib/es/index.js (createUniver), Copyright 2023-present DreamNum Co., Ltd.,
// licensed under the Apache License, Version 2.0, for Roost. Roost installs the individual open-source presets and
// never that meta package (it pulls in @univerjs-pro/*, spec §3.1), so this small wrapper replaces its createUniver.
import { LogLevel, Univer, type IUniverConfig, type LocaleType, type Plugin, type PluginCtor } from "@univerjs/core";
import { FUniver } from "@univerjs/core/facade";
import { defaultTheme } from "@univerjs/themes";

type PluginEntry = PluginCtor<Plugin> | readonly [PluginCtor<Plugin>, unknown];

export interface UniverPreset {
  plugins: readonly PluginEntry[];
}

export interface CreatedUniver {
  univer: Univer;
  univerAPI: FUniver;
}

export function createUniver(
  locale: LocaleType,
  locales: NonNullable<IUniverConfig["locales"]>,
  presets: readonly UniverPreset[],
): CreatedUniver {
  const univer = new Univer({ logLevel: LogLevel.WARN, theme: defaultTheme, locale, locales });
  for (const preset of presets) {
    for (const entry of preset.plugins) {
      const [plugin, config] = Array.isArray(entry) ? entry : [entry, undefined];
      univer.registerPlugin(plugin, config as ConstructorParameters<typeof plugin>[0]);
    }
  }
  return { univer, univerAPI: FUniver.newAPI(univer) };
}
