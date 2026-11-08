"""Compose the YouTube thumbnail from project.json "cover" (poster style: color band on top, big italic headline,
//// stripes + route, stats line, optional logo in a small theme-colored box bottom-right).
usage: python cover.py <project_root>   -> cover/cover_1920.jpg and cover/cover_1280.jpg
The art (cover.art) is usually an AI repaint of a real frame (see image.py)."""
import sys, os, json
from PIL import Image, ImageDraw, ImageFont
R = os.path.abspath(sys.argv[1]); CFG = json.load(open(f'{R}/project.json')); C = CFG['cover']
hexrgb = lambda h: tuple(int(h.lstrip('#')[i:i+2], 16) for i in (0, 2, 4))
BLUE = hexrgb(CFG.get('theme', {}).get('primary', '#1D5FB4')); PAPER = hexrgb(CFG.get('theme', {}).get('paper', '#F4ECDE'))
FB, FI = f'{R}/fonts/Kanit-ExtraBoldItalic.ttf', f'{R}/fonts/Kanit-BoldItalic.ttf'
W, H = 1920, 1080
im = Image.open(f"{R}/{C['art']}").convert('RGB').resize((W, H), Image.LANCZOS)
d = ImageDraw.Draw(im)
def text(xy, s, font, fill, stroke=0, sc=PAPER, anchor='la'): d.text(xy, s, font=font, fill=fill, stroke_width=stroke, stroke_fill=sc, anchor=anchor)
d.rectangle([0, 0, W, 130], fill=BLUE)
text((W // 2, 65), C['band_text'], ImageFont.truetype(FI, 60), 'white', anchor='mm')
text((80, 150), C['headline'], ImageFont.truetype(FB, 170), BLUE, 6)
for i in range(5):
    x0 = 86 + i * 22; d.polygon([(x0 + 14, 385), (x0 + 24, 385), (x0 + 10, 439), (x0, 439)], fill=BLUE)
text((220, 372), C['route'], ImageFont.truetype(FI, 62), BLUE, 5)
text((88, 460), C['stats'], ImageFont.truetype(FI, 54), BLUE, 5)
if C.get('logo'):
    logo = Image.open(f"{R}/{C['logo']}").convert('RGBA')
    bw, px, py = 400, 34, 30
    lw = bw - 2 * px; logo = logo.resize((lw, int(logo.height * lw / logo.width)), Image.LANCZOS)
    if C.get('logo_box', True):
        box = Image.new('RGBA', (bw, logo.height + 2 * py), BLUE + (255,)); box.alpha_composite(logo, (px, py)); logo = box
    im = im.convert('RGBA'); im.alpha_composite(logo, (W - logo.width - 50, H - logo.height - 50)); im = im.convert('RGB')
im.save(f'{R}/cover/cover_1920.jpg', quality=93); im.resize((1280, 720), Image.LANCZOS).save(f'{R}/cover/cover_1280.jpg', quality=92)
print('cover/cover_1280.jpg')
