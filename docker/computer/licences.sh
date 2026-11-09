#!/bin/sh
# Build-time licence scan. Per installed package: the GPL/LGPL/AGPL/SSPL variants named in its Debian copyright
# file (a heuristic). Fails the build on any AGPL or SSPL package, and prints the GPL/LGPL list for the notices.
bad=0
for p in $(dpkg-query -W -f='${Package}\n'); do
  f=/usr/share/doc/$p/copyright
  [ -f "$f" ] || f=$(readlink -f /usr/share/doc/$p 2>/dev/null)/copyright
  [ -f "$f" ] || continue
  l=$(grep -ohE '\b(L?GPL|AGPL|SSPL)[-v ]*[0-9.]*(\+|-only|-or-later)?' "$f" 2>/dev/null | sed 's/ *$//' | sort -u | tr '\n' ',' | sed 's/,$//')
  [ -n "$l" ] || continue
  echo "$p|$(dpkg-query -W -f='${Version}' "$p")|$l"
  case "$l" in *AGPL*|*SSPL*) echo "REFUSED: $p is under $l" >&2; bad=1 ;; esac
done
# Permissive programs Roost calls directly, listed for the notices (C3: roost-input runs xdotool; the browser is
# Brave, MPL-2.0 with its bundled Chromium licences, from Brave's own apt repo).
echo "brave-browser|$(dpkg-query -W -f='${Version}' brave-browser 2>/dev/null)|MPL-2.0"
for p in xdotool libxdo3; do
  echo "$p|$(dpkg-query -W -f='${Version}' "$p" 2>/dev/null)|BSD-3-Clause"
done
[ "$bad" = 0 ] || exit 1
