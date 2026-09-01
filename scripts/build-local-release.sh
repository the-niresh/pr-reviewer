#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
DEST="${1:-$ROOT/dist}"
VERSION=$(python3 -c "import tomllib, pathlib; print(tomllib.loads((pathlib.Path('$ROOT') / 'pyproject.toml').read_text())['project']['version'])")
ASSET="pr-reviewer-${VERSION}-compose.release.yml"
mkdir -p "$DEST"
docker compose -f "$ROOT/compose.release.yml" config > "$DEST/$ASSET"
(cd "$DEST" && sha256sum "$ASSET" > SHA256SUMS)
echo "asset=$DEST/$ASSET"
echo "checksum_file=$DEST/SHA256SUMS"
cat "$DEST/SHA256SUMS"
