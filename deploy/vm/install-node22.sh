#!/usr/bin/env bash
set -euo pipefail

NODE_VERSION="${NODE_VERSION:-v22.23.3}"
PREFIX="${PREFIX:-/opt/lotediretor/node22}"
ARCH="${ARCH:-linux-x64}"
TARBALL="node-${NODE_VERSION}-${ARCH}.tar.xz"
URL="https://nodejs.org/dist/${NODE_VERSION}/${TARBALL}"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

curl -fL --retry 3 -o "$tmp/$TARBALL" "$URL"
rm -rf "$PREFIX"
mkdir -p "$PREFIX"
tar -xJf "$tmp/$TARBALL" -C "$PREFIX" --strip-components=1

"$PREFIX/bin/node" --version
"$PREFIX/bin/npm" --version
