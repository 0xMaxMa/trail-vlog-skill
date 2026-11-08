#!/bin/bash
# usage: setup.sh <project_root>
# Creates the project layout, a Python venv with deps, and downloads Kanit fonts.
set -e
ROOT="${1:?project root required}"
SK="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$ROOT"/{raw,work/{audio,stt,frames,sheets,proxy,test},music,garmin,sprites,cover,fonts,ref,output}
command -v ffmpeg >/dev/null || { echo "ffmpeg missing: brew install ffmpeg (needs libass + freetype)"; exit 1; }
ffmpeg -hide_banner -filters 2>/dev/null | grep -q " ass " || echo "WARNING: ffmpeg has no libass (subtitles/graphics won't burn in)"
[ -x "$ROOT/work/venv/bin/python" ] || python3 -m venv "$ROOT/work/venv"
"$ROOT/work/venv/bin/pip" -q install fitparse pillow numpy 2>&1 | grep -v notice || true
for f in Kanit-Bold Kanit-BoldItalic Kanit-ExtraBoldItalic Kanit-SemiBold; do
  [ -s "$ROOT/fonts/$f.ttf" ] || curl -sfL -o "$ROOT/fonts/$f.ttf" "https://raw.githubusercontent.com/google/fonts/main/ofl/kanit/$f.ttf"
done
cp -n "$SK/templates/project_template.json" "$ROOT/project.json" 2>/dev/null || true
cp -n "$SK/templates/edl_template.py" "$ROOT/work/edl.py" 2>/dev/null || true
cp -n "$SK"/assets/*.png "$ROOT/sprites/" 2>/dev/null || true
ffmpeg -hide_banner -encoders 2>/dev/null | grep -q hevc_videotoolbox && echo "encoder: Apple VideoToolbox (fast)" || echo "encoder: libx265/libx264 (software, slower)"
echo "ready: $ROOT"
