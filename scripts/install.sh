#!/bin/sh
set -eu

ARCHIVE=""
CHECKSUM_FILE=""
PREFIX=""

while [ $# -gt 0 ]; do
  case "$1" in
    --archive)
      ARCHIVE="$2"
      shift 2
      ;;
    --checksum-file)
      CHECKSUM_FILE="$2"
      shift 2
      ;;
    --prefix)
      PREFIX="$2"
      shift 2
      ;;
    *)
      echo "unknown option: $1" >&2
      exit 2
      ;;
  esac
done

if [ -z "$ARCHIVE" ] || [ -z "$CHECKSUM_FILE" ] || [ -z "$PREFIX" ]; then
  echo "usage: install.sh --archive FILE --checksum-file SHA256SUMS --prefix DIR" >&2
  exit 2
fi

NAME=$(basename "$ARCHIVE")
VERIFY="${TMPDIR:-/tmp}/pr-reviewer-verify-$$"
mkdir -p "$VERIFY"
cp "$ARCHIVE" "$VERIFY/$NAME"
cp "$CHECKSUM_FILE" "$VERIFY/SHA256SUMS"
if ! (cd "$VERIFY" && sha256sum -c SHA256SUMS); then
  rm -rf "$VERIFY"
  exit 1
fi
mkdir -p "$PREFIX"
cp "$VERIFY/$NAME" "$PREFIX/$NAME"
rm -rf "$VERIFY"
