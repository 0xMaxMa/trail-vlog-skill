#!/bin/bash
# usage: ingest.sh <project_root>
# For every raw clip: 16 kHz mono audio, a 960x540/30fps proxy, and 1 frame / 4 s for contact sheets.
# Then packs frames into 6x5 contact sheets (work/sheets/sNN.jpg) and prints which clips each sheet covers.
ROOT="${1:?project root required}"; cd "$ROOT/work" || exit 1
FONT=/System/Library/Fonts/Supplemental/Silom.ttf; [ -f "$FONT" ] || FONT=$(fc-match -f '%{file}' sans 2>/dev/null)
if ffmpeg -hide_banner -encoders 2>/dev/null | grep -q h264_videotoolbox; then ENC="-c:v h264_videotoolbox -b:v 3M"; else ENC="-c:v libx264 -preset veryfast -b:v 3M"; fi
one() {
  f=$1; b=$(basename "$f"); b=${b%.*}; n=$(echo "$b" | awk -F_ '{print $3}'); [ -n "$n" ] || n=$b
  [ -s audio/$n.mp3 ] || ffmpeg -hide_banner -loglevel error -nostdin -y -i "$f" -vn -ac 1 -ar 16000 -b:a 48k audio/$n.mp3
  [ -s proxy/$n.mp4 ] || { ffmpeg -hide_banner -loglevel error -nostdin -y -i "$f" -vf "fps=30,scale=960:540" $ENC -c:a aac -b:a 128k -ar 48000 -ac 2 proxy/.$n.mp4 && mv proxy/.$n.mp4 proxy/$n.mp4; }
  ls frames/${n}_001.jpg >/dev/null 2>&1 || ffmpeg -hide_banner -loglevel quiet -nostdin -y -i proxy/$n.mp4 -vf "fps=1/4,scale=400:-2,drawtext=fontfile=$FONT:text='$n %{eif\:t\:d}s':x=6:y=6:fontsize=22:fontcolor=yellow:box=1:boxcolor=black@0.6" frames/${n}_%03d.jpg
}
export -f one; export ENC FONT
ls "$ROOT"/raw/*.[Mm][Pp]4 "$ROOT"/raw/*.[Mm][Oo][Vv] 2>/dev/null | xargs -P 4 -I{} bash -c 'one "{}"'
rm -f sheets/*.jpg; ls frames/*.jpg | sort > list.txt; split -l 30 list.txt pp_; i=0
for p in pp_*; do i=$((i+1)); awk '{print "file \x27" ENVIRON["PWD"] "/" $0 "\x27"}' $p > $p.ff
  ffmpeg -hide_banner -loglevel error -y -f concat -safe 0 -i $p.ff -vf tile=6x5 -frames:v 1 sheets/s$(printf %02d $i).jpg
  echo "s$(printf %02d $i): $(basename $(head -1 $p) .jpg) .. $(basename $(tail -1 $p) .jpg)"; done; rm -f pp_*
