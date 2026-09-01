#!/bin/sh
set -eu

DELETE=0
CONFIRM=0

while [ $# -gt 0 ]; do
  case "$1" in
    --delete-data)
      DELETE=1
      shift
      ;;
    --confirm-delete)
      CONFIRM=1
      shift
      ;;
    *)
      echo "unknown option: $1" >&2
      exit 2
      ;;
  esac
done

if [ "$DELETE" -eq 1 ]; then
  if [ "$CONFIRM" -ne 1 ]; then
    echo "deleting data requires --confirm-delete" >&2
    exit 1
  fi
  reviewer uninstall --delete-data --confirm-delete
  exit $?
fi

reviewer uninstall
