# Vertical 9:16 teaser (FB Reels / YouTube Shorts) from the final edit: themed poster frame + 16:9 video window
# + CTA pill + whole-course elevation profile + end card. Settings in project.json "reel" (see templates/project_template.json).
# usage (cwd <project>/work):  venv/bin/python <skill>/scripts/reel.py <project>
import json, os, subprocess, sys
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else '..')
CFG = json.load(open(f'{ROOT}/project.json'))
R = CFG.get('reel', {})
T = CFG.get('theme', {})
hexrgb = lambda h: tuple(int(h.lstrip('#')[i:i + 2], 16) for i in (0, 2, 4))
BLUE, CREAM = hexrgb(T.get('primary', '#0863AA')), hexrgb(T.get('paper', '#F2F0E9'))
CHIP = tuple(int(c + (255 - c) * 0.8) for c in BLUE)
W, H = 1080, 1920
VX, VY, VW, VH = 40, 560, 1000, 562
A, B = R.get('a', 0.0), R.get('b', 45.5)          # span of the final edit to use (hook + montage ending on the title works well)
END = R.get('end_s', 4.5)
SRC = f"{ROOT}/output/{CFG.get('output_name', 'trail_vlog')}_final.mp4"
os.makedirs(f'{ROOT}/reels', exist_ok=True)
F = lambda s: ImageFont.truetype(f'{ROOT}/fonts/Kanit-Bold.ttf', s)
FS = lambda s: ImageFont.truetype(f'{ROOT}/fonts/Kanit-SemiBold.ttf', s)

im = Image.new('RGBA', (W, H), BLUE); d = ImageDraw.Draw(im)
d.rounded_rectangle([26, 26, W - 26, H - 26], 18, fill=CREAM)
d.text((64, 52), R.get('headline', CFG.get('title', '')), font=F(190), fill=BLUE)
d.text((70, 290), R.get('subline', ''), font=F(34), fill=BLUE)
for i, (lab, th, val) in enumerate(R.get('chips', [])[:2]):
    x, y = 64 + 496 * i, 360
    d.text((x, y), lab, font=F(28), fill=BLUE); d.text((x, y + 34), th, font=FS(22), fill=BLUE)
    d.rectangle([x + 230, y + 4, x + 470, y + 62], fill=CHIP); d.text((x + 248, y + 6), val, font=F(40), fill=BLUE)
tag, fs = R.get('tagline', ''), 40
while tag and d.textlength(tag, font=F(fs)) > W - 128: fs -= 1
d.text((64, 448 + (40 - fs) // 2), tag, font=F(fs), fill=BLUE)
d.line([60, 525, W - 60, 525], fill=BLUE, width=4)
d.rectangle([VX - 7, VY - 7, VX + VW + 6, VY + VH + 6], fill=BLUE)
d.rectangle([VX, VY, VX + VW - 1, VY + VH - 1], fill=(0, 0, 0, 0))
cta = R.get('cta', 'ดูคลิปเต็ม · ลิงก์ในคอมเมนต์'); cy = VY + VH + 40
d.rounded_rectangle([90, cy, W - 90, cy + 86], 43, fill=BLUE)
d.text((W / 2, cy + 43), cta, font=F(44), fill='white', anchor='mm')
# whole-course elevation profile with station boxes (records.json: [t, hr, alt, dist_m, lat, lon])
rec = json.load(open(f'{ROOT}/garmin/records.json')) if os.path.exists(f'{ROOT}/garmin/records.json') else []
if rec:
    pts = [(r[3] / 1000, r[2]) for r in rec]
    kmax = pts[-1][0]; emin = min(e for _, e in pts) - 80; emax = max(e for _, e in pts) + 80
    px0, px1, py0, py1 = 80, 1000, 1330, 1580
    X = lambda k: px0 + (px1 - px0) * min(k, kmax) / kmax
    Y = lambda e: py1 - (py1 - py0) * (e - emin) / (emax - emin)
    step = max(1, len(pts) // 1200)
    d.polygon([(px0, py1)] + [(X(k), Y(e)) for k, e in pts[::step]] + [(px1, py1)], fill=BLUE)
    for code, _, km, _ in CFG.get('stations', []):
        x = X(km); e = min(pts, key=lambda p: abs(p[0] - km))[1]
        for yy in range(int(py0 - 30), int(Y(e)), 10): d.line([x, yy, x, yy + 5], fill=BLUE, width=2)
        d.ellipse([x - 7, Y(e) - 7, x + 7, Y(e) + 7], fill='white', outline=BLUE, width=3)
        d.rectangle([x - 26, py1 + 14, x + 26, py1 + 50], outline=BLUE, width=3, fill=CREAM)
        d.text((x, py1 + 32), {'START': 'S', 'FINISH': 'F'}.get(code, code), font=F(24), fill=BLUE, anchor='mm')
        d.text((x, py1 + 66), f'{km:g}', font=FS(20), fill=BLUE, anchor='mm')
frame = f'{ROOT}/reels/frame.png'; im.save(frame)

end1, end2 = R.get('end_text', ['ดูคลิปเต็ม', 'ลิงก์ในคอมเมนต์'])
bgr = '&H00%02X%02X%02X&' % BLUE[::-1]
ts = lambda s: f'0:{int(s // 60):02d}:{s % 60:05.2f}'
dur = B - A
ass = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: End,Kanit,84,&H00FFFFFF,&H00FFFFFF,{bgr},&H64000000,1,0,0,0,100,100,0,0,1,0,0,5,60,60,0,0

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 1,{ts(dur)},{ts(dur + END)},End,,0,0,0,,{{\\pos(540,{VY + VH // 2})\\fad(300,0)}}{end1}\\N{{\\fs56}}{end2}
"""
open(f'{ROOT}/reels/reel.ass', 'w').write(ass)
out = f"{ROOT}/reels/{CFG.get('output_name', 'trail_vlog')}_reel.mp4"
tot = dur + END
hexc = '0x%02X%02X%02X' % BLUE
fc = (f"[0:v]fps=30,scale={VW}:{VH}:flags=lanczos,tpad=stop_mode=clone:stop_duration={END},"
      f"drawbox=x=0:y=0:w=iw:h=ih:color={hexc}@0.85:t=fill:enable='gte(t,{dur})'[fg];"
      f"color=c=black:s={W}x{H}:r=30:d={tot}[base];[base][fg]overlay={VX}:{VY}[b1];[b1][1:v]overlay=0:0:shortest=1,format=yuv420p,"
      f"ass=reels/reel.ass:fontsdir=fonts,fade=t=out:st={tot - 0.6}:d=0.6[v];"
      f"[0:a]afade=t=out:st={dur - 1}:d={END + 1},apad=whole_dur={tot}[a]")
os.chdir(ROOT)
subprocess.run(['ffmpeg', '-v', 'error', '-y', '-ss', str(A), '-t', str(dur), '-i', SRC, '-loop', '1', '-i', frame, '-filter_complex', fc,
                '-map', '[v]', '-map', '[a]', '-c:v', 'libx264', '-preset', 'medium', '-crf', '19', '-pix_fmt', 'yuv420p',
                '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', '-t', str(tot), out], check=True)
print('wrote', out)
