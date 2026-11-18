"""Compose the YouTube thumbnail from project.json "cover" (poster style: color band on top, big italic headline,
//// stripes + route, stats line, optional logo in a small theme-colored box bottom-right).
usage: python cover.py <project_root> [art] [name] [focus_x 0..1] [focus_y 0..1]
   -> cover/<name>_1920.jpg and cover/<name>_1280.jpg   (name defaults to 'cover', art to project.json cover.art)
The art is an AI repaint of a real frame (see image.py) or a real photo (e.g. an event photographer's); it is
cover-cropped to 16:9 around (focus_x, focus_y), so put the runner off-centre to the right to leave room for the text."""
import sys, os, json
from PIL import Image, ImageDraw, ImageFont
R = os.path.abspath(sys.argv[1]); CFG = json.load(open(f'{R}/project.json')); C = CFG['cover']
hexrgb = lambda h: tuple(int(h.lstrip('#')[i:i+2], 16) for i in (0, 2, 4))
BLUE = hexrgb(CFG.get('theme', {}).get('primary', '#1D5FB4')); PAPER = hexrgb(CFG.get('theme', {}).get('paper', '#F4ECDE'))
FB, FI = f'{R}/fonts/Kanit-ExtraBoldItalic.ttf', f'{R}/fonts/Kanit-BoldItalic.ttf'
W, H = 1920, 1080
from PIL import ImageOps
A = sys.argv
art = A[2] if len(A) > 2 else C['art']; name = A[3] if len(A) > 3 else 'cover'
fx = float(A[4]) if len(A) > 4 else 0.5; fy = float(A[5]) if len(A) > 5 else 0.5
im = ImageOps.exif_transpose(Image.open(art if os.path.isabs(art) else f"{R}/{art}")).convert('RGB')
sc = max(W / im.width, H / im.height); im = im.resize((round(im.width * sc), round(im.height * sc)), Image.LANCZOS)
x0, y0 = int((im.width - W) * fx), int((im.height - H) * fy); im = im.crop((x0, y0, x0 + W, y0 + H))
PHOTO = C.get('shade', len(A) > 2)   # real-photo variants: dark wash + white type with theme-colored outline
if PHOTO:   # soft dark wash behind the title area so the poster text reads on busy photos
    sh = Image.new('L', (W, H), 0); ds = ImageDraw.Draw(sh)
    for i in range(W): ds.line([(i, 0), (i, H)], fill=int(150 * max(0, 1 - i / (W * 0.62)) ** 1.6))
    im = Image.composite(Image.new('RGB', (W, H), (8, 18, 40)), im, sh)
d = ImageDraw.Draw(im)
def text(xy, s, font, fill, stroke=0, sc=PAPER, anchor='la'): d.text(xy, s, font=font, fill=fill, stroke_width=stroke, stroke_fill=sc, anchor=anchor)
d.rectangle([0, 0, W, 130], fill=BLUE)
text((W // 2, 65), C['band_text'], ImageFont.truetype(FI, 60), 'white', anchor='mm')
FG, SC = ('white', BLUE) if PHOTO else (BLUE, PAPER)
text((80, 150), C['headline'], ImageFont.truetype(FB, 170), FG, 9 if PHOTO else 6, SC)
for i in range(5):
    x0 = 86 + i * 22; d.polygon([(x0 + 14, 385), (x0 + 24, 385), (x0 + 10, 439), (x0, 439)], fill=FG, outline=SC)
text((220, 372), C['route'], ImageFont.truetype(FI, 62), FG, 6, SC)
text((88, 460), C['stats'], ImageFont.truetype(FI, 54), FG, 6, SC)
if C.get('logo'):
    logo = Image.open(f"{R}/{C['logo']}").convert('RGBA')
    bw, px, py = 400, 34, 30
    lw = bw - 2 * px; logo = logo.resize((lw, int(logo.height * lw / logo.width)), Image.LANCZOS)
    if C.get('logo_box', True):
        box = Image.new('RGBA', (bw, logo.height + 2 * py), BLUE + (255,)); box.alpha_composite(logo, (px, py)); logo = box
    im = im.convert('RGBA'); im.alpha_composite(logo, (W - logo.width - 50, H - logo.height - 50)); im = im.convert('RGB')
os.makedirs(f'{R}/cover', exist_ok=True)
im.save(f'{R}/cover/{name}_1920.jpg', quality=93); im.resize((1280, 720), Image.LANCZOS).save(f'{R}/cover/{name}_1280.jpg', quality=92)
print(f'cover/{name}_1280.jpg')
