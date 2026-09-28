#!/usr/bin/env bash
set -euo pipefail

MARTIN_VERSION="${MARTIN_VERSION:-1.16.1}"
PREFIX="${PREFIX:-/opt/lotediretor/martin}"
ASSET="martin-x86_64-unknown-linux-gnu.tar.gz"
URL="https://github.com/maplibre/martin/releases/download/martin-v${MARTIN_VERSION}/${ASSET}"
SHA256="${SHA256:-cd37c6d55914ba118628d38d7f8204bdb385c75a2ff1839bf26b263ea4f302c1}"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

curl -fL --retry 3 -o "$tmp/$ASSET" "$URL"
echo "$SHA256  $tmp/$ASSET" | sha256sum -c -

rm -rf "$PREFIX"
mkdir -p "$PREFIX"
tar -xzf "$tmp/$ASSET" -C "$PREFIX"

"$PREFIX/martin" --version
