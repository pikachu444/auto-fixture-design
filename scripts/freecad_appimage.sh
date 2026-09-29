#!/bin/sh
set -eu
if [ -z "${FREECAD_APPIMAGE:-}" ]; then
  echo 'FREECAD_APPIMAGE is not set' >&2
  exit 1
fi
export APPIMAGE_EXTRACT_AND_RUN=1
export QT_QPA_PLATFORM=offscreen
if [ "$#" -ne 1 ]; then
  echo 'Expected one trusted worker script path' >&2
  exit 2
fi
export FIXTURE_FREECAD_SCRIPT="$1"
# The AppImage's --console opens a Python prompt; it does not run a .py argument.
printf '%s\n' 'exec(compile(open(__import__("os").environ["FIXTURE_FREECAD_SCRIPT"]).read(), "<fixture-worker>", "exec"))' | "$FREECAD_APPIMAGE" --console
