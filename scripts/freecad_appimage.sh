#!/bin/sh
set -eu
if [ -z "${FREECAD_APPIMAGE:-}" ]; then
  echo 'FREECAD_APPIMAGE is not set' >&2
  exit 1
fi
export APPIMAGE_EXTRACT_AND_RUN=1
export QT_QPA_PLATFORM=offscreen
exec "$FREECAD_APPIMAGE" --console "$@"
