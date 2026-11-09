#!/usr/bin/env bash
# Publish the phone app for the in-app update (app restructure slice 2).
#
# Reads the version from mobile/pubspec.yaml, builds a slim release APK, copies it to
# ~/Roost/mobile/roost-<version>+<build>.apk and writes latest.json there
# atomically. The gateway serves both (GET /api/mobile/latest, /api/mobile/apk/<file>).
#
#   make mobile-publish                  # or: scripts/publish_mobile.sh "one line of notes"
#
# It always makes a release build for 64-bit ARM phones. Without
# mobile/android/key.properties it is signed with this Mac's own debug keystore.
# Android installs an update only when it is signed with the same key as the
# installed app, so keep publishing from this Mac with the same key.
#
# Overrides (tests): ROOST_MOBILE_DIR (where to publish), ROOST_MOBILE_SRC (the
# Flutter project), FLUTTER (the flutter command).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="${ROOST_MOBILE_SRC:-$REPO_ROOT/mobile}"
OUT="${ROOST_MOBILE_DIR:-$HOME/Roost/mobile}"
FLUTTER="${FLUTTER:-flutter}"
NOTES="${1:-}"

fail() { echo "publish_mobile: $*" >&2; exit 1; }

line="$(grep -E '^version:[[:space:]]*' "$SRC/pubspec.yaml" | head -n 1 || true)"
[[ -n "$line" ]] || fail "no version: line in $SRC/pubspec.yaml"
full="$(echo "$line" | sed -E 's/^version:[[:space:]]*//; s/[[:space:]]+$//')"
[[ "$full" =~ ^([0-9]+\.[0-9]+\.[0-9]+)\+([0-9]+)$ ]] || fail "version must look like 1.0.1+2 (got '$full')"
version="${BASH_REMATCH[1]}"
build="${BASH_REMATCH[2]}"
(( build >= 1 )) || fail "the build number must be 1 or more"
app_line="$(grep -E "^const appVersion = '" "$SRC/lib/app_version.dart" 2>/dev/null | head -n 1 || true)"
[[ "$app_line" == "const appVersion = '$full';" ]] || fail "lib/app_version.dart must say '$full' like pubspec.yaml (the app compares it to latest.json)"
[[ ${#NOTES} -le 200 ]] || fail "notes are one line of at most 200 characters"
[[ "$NOTES" != *$'\n'* ]] || fail "notes are one line"

# Always a release build for 64-bit ARM phones only (a debug build is ~150 MB). Without key.properties Gradle signs
# it with the machine's debug key, the same key as the debug builds already installed, so updates keep working.
if [[ -f "$SRC/android/key.properties" ]]; then
  signed="the key in android/key.properties"
else
  signed="the debug key"
fi
build_args=(build apk --release --target-platform android-arm64)
echo "publish_mobile: building a release APK of $version+$build (--target-platform android-arm64), signed with $signed"
(cd "$SRC" && "$FLUTTER" "${build_args[@]}")

apk="$SRC/build/app/outputs/flutter-apk/app-release.apk"
[[ -f "$apk" ]] || fail "the build did not make $apk"

name="roost-$version+$build.apk"
mkdir -p "$OUT"
cp "$apk" "$OUT/.$name.tmp"
mv -f "$OUT/.$name.tmp" "$OUT/$name"
sha="$(shasum -a 256 "$OUT/$name" | awk '{print $1}')"

tmp="$OUT/.latest.json.tmp"
python3 - "$version" "$build" "$name" "$sha" "$NOTES" > "$tmp" <<'PY'
import json, sys
version, build, name, sha, notes = sys.argv[1:]
print(json.dumps({"version": version, "build": int(build), "file": name, "sha256": sha, "notes": notes}))
PY
mv -f "$tmp" "$OUT/latest.json"
echo "publish_mobile: published $name (release build, $(du -h "$OUT/$name" | cut -f1), sha256 $sha) to $OUT"
