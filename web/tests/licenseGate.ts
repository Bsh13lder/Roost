// The web license gate (spec §3.1, §10.1; M2 D4). Univer's paid line never
// ships: the @univerjs/presets meta package pulls in @univerjs-pro/* (no
// license field), so Roost installs the individual open-source presets only.
export interface LockFile {
  packages?: Record<string, { license?: string; dev?: boolean }>;
}

// Spec §10.3: Roost ships only MIT, Apache-2.0, BSD (0BSD, 2- and 3-clause), ISC, MPL-2.0 or HPND code
// (HPND: the owner approved it on 2026-10-21 for Pillow).
// Dev-only tools (the test runner, the bundler) are not shipped, so only runtime packages count.
export const ALLOWED_RUNTIME_LICENSES: ReadonlySet<string> = new Set([
  "MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "0BSD", "ISC", "MPL-2.0", "HPND",
]);

// Packages whose package.json has no license field, each reviewed by hand.
export const REVIEWED_NO_LICENSE_FIELD: Readonly<Record<string, string>> = {
  "node_modules/@univerjs/telemetry":
    "Apache-2.0: its LICENSE file and source headers (DreamNum Co., Ltd.); a dependency of @univerjs/sheets-ui. Reviewed 2026-10-14.",
};

function pathsMatching(lock: LockFile, pattern: RegExp): string[] {
  return Object.keys(lock.packages ?? {}).filter((path) => pattern.test(path)).sort();
}

export function proPackages(lock: LockFile): string[] {
  return pathsMatching(lock, /(^|\/)node_modules\/@univerjs-pro\//);
}

export function metaPresets(lock: LockFile): string[] {
  return pathsMatching(lock, /(^|\/)node_modules\/@univerjs\/presets$/);
}

export function disallowedRuntimeLicenses(lock: LockFile): string[] {
  return Object.entries(lock.packages ?? {})
    .filter(([path, meta]) => path !== "" && !meta.dev && !(path in REVIEWED_NO_LICENSE_FIELD))
    .filter(([, meta]) => !ALLOWED_RUNTIME_LICENSES.has(meta.license ?? ""))
    .map(([path, meta]) => `${path} ${meta.license ?? "(none)"}`)
    .sort();
}

export function unreviewedWithoutLicense(lock: LockFile): string[] {
  return Object.entries(lock.packages ?? {})
    .filter(([path, meta]) => path !== "" && !meta.license && !(path in REVIEWED_NO_LICENSE_FIELD))
    .map(([path]) => path)
    .sort();
}
