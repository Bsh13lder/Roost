// @vitest-environment node
import { readdirSync, readFileSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import {
  disallowedRuntimeLicenses, metaPresets, proPackages, unreviewedWithoutLicense, type LockFile,
} from "./licenseGate";

const lock = JSON.parse(readFileSync(new URL("../package-lock.json", import.meta.url), "utf8")) as LockFile;

describe("license gate (spec §3.1)", () => {
  it("installs no @univerjs-pro package and not the @univerjs/presets meta package", () => {
    expect(proPackages(lock)).toEqual([]);
    expect(metaPresets(lock)).toEqual([]);
  });

  it("fails on a test @univerjs-pro package, nested or not", () => {
    const bad: LockFile = { packages: {
      "": {},
      "node_modules/@univerjs-pro/license": { license: "UNLICENSED" },
      "node_modules/@univerjs/x/node_modules/@univerjs-pro/collaboration": {},
      "node_modules/@univerjs/core": { license: "Apache-2.0" },
    } };
    expect(proPackages(bad)).toEqual([
      "node_modules/@univerjs-pro/license", "node_modules/@univerjs/x/node_modules/@univerjs-pro/collaboration",
    ]);
    expect(metaPresets({ packages: { "node_modules/@univerjs/presets": { license: "Apache-2.0" } } }))
      .toEqual(["node_modules/@univerjs/presets"]);
  });

  it("every installed package names its license or has a reviewed entry", () => {
    expect(unreviewedWithoutLicense(lock)).toEqual([]);
    expect(unreviewedWithoutLicense({ packages: { "node_modules/mystery": {} } })).toEqual(["node_modules/mystery"]);
  });

  it("every package the app ships is MIT, Apache-2.0, BSD, ISC, MPL-2.0 or HPND (Radix and react-day-picker included)", () => {
    expect(disallowedRuntimeLicenses(lock)).toEqual([]);
    expect(lock.packages?.["node_modules/@radix-ui/react-select"]?.license).toBe("MIT");
    expect(lock.packages?.["node_modules/react-day-picker"]?.license).toBe("MIT");
    expect(disallowedRuntimeLicenses({ packages: {
      "": {},
      "node_modules/gpl-thing": { license: "GPL-3.0" },
      "node_modules/vitest": { license: "MIT", dev: true },
      "node_modules/caniuse-lite": { license: "CC-BY-4.0", dev: true },
      "node_modules/@univerjs/telemetry": {},
    } })).toEqual(["node_modules/gpl-thing GPL-3.0"]);
  });

  it("HPND (approved by the owner on 2026-10-21 for Pillow) is allowed, GPL still is not", () => {
    expect(disallowedRuntimeLicenses({ packages: {
      "": {}, "node_modules/hpnd-thing": { license: "HPND" }, "node_modules/gpl-thing": { license: "GPL-3.0" },
    } })).toEqual(["node_modules/gpl-thing GPL-3.0"]);
  });

  it("noVNC is MPL-2.0 and imported only by web/src/lib/novnc.ts", () => {
    expect(lock.packages?.["node_modules/@novnc/novnc"]?.license).toBe("MPL-2.0");
    const src = fileURLToPath(new URL("../src/", import.meta.url));
    const files = (dir: string): string[] => readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
      const path = join(dir, entry.name);
      return entry.isDirectory() ? files(path) : /\.(ts|tsx)$/.test(entry.name) ? [path] : [];
    });
    const importers = files(src)
      .filter((path) => /["']@novnc\/novnc/.test(readFileSync(path, "utf8")))
      .filter((path) => !path.endsWith(".d.ts"))
      .map((path) => relative(src, path));
    expect(importers).toEqual(["lib/novnc.ts"]);
  });
});
