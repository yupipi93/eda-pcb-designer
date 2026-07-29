#!/usr/bin/env bash
# Fetch the freerouting autorouter JAR (not committed to the repo — 64 MB).
#
# Downloads the pinned release from the official freerouting GitHub releases
# and verifies its SHA-256 before installing it as vendor/freerouting.jar.
#
# Usage:  ./vendor/fetch-freerouting.sh
set -euo pipefail

VERSION="2.1.0"
SHA256="2c07d58f75dac03782664081e7a58b41c25400d871a9fcf166a2ea6fe60d5def"
URL="https://github.com/freerouting/freerouting/releases/download/v${VERSION}/freerouting-${VERSION}.jar"

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
JAR="${HERE}/freerouting.jar"

if [[ -f "$JAR" ]] && echo "${SHA256}  ${JAR}" | sha256sum --check --status; then
    echo "OK: freerouting v${VERSION} already present at ${JAR}"
    exit 0
fi

echo "Downloading freerouting v${VERSION} (~64 MB)..."
TMP="$(mktemp "${HERE}/freerouting.jar.XXXXXX")"
trap 'rm -f "$TMP"' EXIT
curl -fSL --retry 3 -o "$TMP" "$URL"

echo "${SHA256}  ${TMP}" | sha256sum --check --status || {
    echo "ERROR: SHA-256 mismatch — refusing to install. Delete and retry." >&2
    exit 1
}

mv "$TMP" "$JAR"
trap - EXIT
echo "OK: installed ${JAR} (v${VERSION}, sha256 verified)"
