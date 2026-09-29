#!/usr/bin/env bash
# lib/auth is vendored in client-web and admin-web (separate Next.js apps on
# separate origins). They must stay byte-identical; edit client-web and run
# this script with --sync to copy.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SRC="$ROOT/apps/client-web/lib/auth"
DST="$ROOT/apps/admin-web/lib/auth"
if [[ "${1:-}" == "--sync" ]]; then
  rm -rf "$DST" && cp -r "$SRC" "$DST" && echo "synced $DST"
  exit 0
fi
diff -r "$SRC" "$DST" && echo "vendored auth libraries are identical"
