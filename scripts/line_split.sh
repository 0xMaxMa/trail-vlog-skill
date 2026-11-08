#!/bin/bash
# Split the final video into small 720p parts for LINE/chat apps, cutting at given timeline seconds.
# usage: line_split.sh <final.mp4> <out_prefix> <t0> <t1> ... <tEnd>
# e.g.   line_split.sh output/trail_vlog_final.mp4 output/trail_vlog_LINE 0 178.3 351.2 478.1 571.15
# Pick cut points at section starts (build.py --plan prints them) so no joke is cut; aim <= 3 min per part.
IN=$1; PRE=$2; shift 2; T=("$@"); N=$((${#T[@]} - 1))
FONT=$(ls "$(dirname "$IN")/../fonts/Kanit-BoldItalic.ttf" 2>/dev/null || echo /System/Library/Fonts/Supplemental/Silom.ttf)
if ffmpeg -hide_banner -encoders 2>/dev/null | grep -q h264_videotoolbox; then ENC="-c:v h264_videotoolbox -b:v 2300k -maxrate 3000k -bufsize 4600k -profile:v high"; else ENC="-c:v libx264 -preset medium -b:v 2300k -maxrate 3000k -bufsize 4600k"; fi
for i in $(seq 1 $N); do
  a=${T[$((i-1))]}; b=${T[$i]}; d=$(echo "$b - $a" | bc)
  ffmpeg -hide_banner -loglevel error -y -ss $a -t $d -i "$IN" -vf "scale=1280:720:flags=lanczos,drawtext=fontfile=$FONT:text='$i/$N':x=24:y=h-th-24:fontsize=34:fontcolor=white:box=1:boxcolor=0x1D5FB4@0.9:boxborderw=10" $ENC -pix_fmt yuv420p -c:a aac -b:a 128k -movflags +faststart "${PRE}_${i}of${N}.mp4"
  echo "part $i/$N: ${d}s $(ls -lh "${PRE}_${i}of${N}.mp4" | awk '{print $5}')"
done
