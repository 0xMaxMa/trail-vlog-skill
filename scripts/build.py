"""Build a trail vlog from work/edl.py + project.json.
usage (cwd = <project>/work, or TRAIL_ROOT=<project>):  python build.py proxy|final [--plan]
  --plan  only prints the timeline (sections, start times, total length)
  proxy   fast 960x540 review cut      final  3840x2160 (40 Mbps HEVC)
Env: XI_KEY (ElevenLabs) for music generation."""
import json, glob, os, subprocess, sys, math, bisect
ROOT = os.environ.get('TRAIL_ROOT') or os.path.dirname(os.path.abspath(os.getcwd()))
W = os.path.join(ROOT, 'work')
os.chdir(W)
CFG = json.load(open(os.path.join(ROOT, 'project.json')))
MODE = sys.argv[1] if len(sys.argv) > 1 else 'proxy'
FINAL = MODE == 'final'
OW, OH = (3840, 2160) if FINAL else (960, 540)
FPS = 30
OFFSET = CFG.get('camera_offset_s', 0)      # seconds the camera clock is FAST vs real time
PRESTART_KM = CFG.get('prestart_km', 0.0)    # distance covered before the watch was started
SEGDIR = f'seg_{MODE}'
os.makedirs(SEGDIR, exist_ok=True)

ns = {}; exec(open('edl.py').read(), ns); SECTIONS = ns['S']


def _has_enc(name):
    try:
        return name in subprocess.run(['ffmpeg', '-hide_banner', '-encoders'], capture_output=True, text=True).stdout
    except Exception: return False
HW = _has_enc('hevc_videotoolbox') and sys.platform == 'darwin'   # Apple Silicon hardware encoder; else libx265/libx264
def venc(hevc_bitrate, h264_bitrate):
    if FINAL:
        return (['-c:v', 'hevc_videotoolbox', '-b:v', hevc_bitrate, '-tag:v', 'hvc1'] if HW else
                ['-c:v', 'libx265', '-preset', 'medium', '-b:v', hevc_bitrate, '-tag:v', 'hvc1', '-x265-params', 'log-level=error'])
    return ['-c:v', 'h264_videotoolbox', '-b:v', h264_bitrate] if HW else ['-c:v', 'libx264', '-preset', 'veryfast', '-b:v', h264_bitrate]

def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode: print(' '.join(cmd)); print(r.stderr[-2000:]); sys.exit(1)
    return r.stdout

def raw_path(c):
    vids = [p for p in (glob.glob(f'{ROOT}/raw/*_{c}_*.*') or glob.glob(f'{ROOT}/raw/{c}.*')) if p.lower().endswith(('.mp4', '.mov'))]
    return sorted(vids, key=lambda p: ('_' + c + '_') not in os.path.basename(p))[0]
def src(c): return raw_path(c) if FINAL else f'proxy/{c}.mp4'
def cam_start(c):
    """Local wall-clock second-of-day when the clip started (camera clock, before OFFSET correction)."""
    name = os.path.basename(raw_path(c))
    if name.startswith('DJI_') and len(name.split('_')[1]) >= 14:
        hms = name.split('_')[1][8:14]
        return int(hms[:2]) * 3600 + int(hms[2:4]) * 60 + int(hms[4:6])
    ct = run(['ffprobe', '-v', 'error', '-show_entries', 'format_tags=creation_time', '-of', 'csv=p=0', raw_path(c)]).strip()
    import datetime as _dt
    t = _dt.datetime.fromisoformat(ct.replace('Z', '+00:00')) + _dt.timedelta(hours=CFG.get('utc_offset_h', 7))
    return t.hour * 3600 + t.minute * 60 + t.second

# ---------- speech tightening ----------
SKIP_EV = ('เดิน', 'วิ่ง', 'ฝน', 'น้ำ', 'ดนตรี', 'มอเตอร์', 'ไก่', 'ถุงมือ', 'พูดแทรก', 'คุย', 'ไอ')
WORDS = {}
def words(c):
    if c not in WORDS:
        d = json.load(open((glob.glob(f'stt/{c}.json') or glob.glob(f'stt/*_{c}_*.json'))[0]))
        ws = []
        for w in d['words']:
            if w['type'] == 'spacing': continue
            if w['type'] == 'audio_event' and any(k in w['text'] for k in SKIP_EV): continue
            ws.append((w['start'], w['end']))
        WORDS[c] = ws
    return WORDS[c]

def pieces_for(s):
    a, b = s['a'], s['b']
    if s['mode'] != 'sp': return [(a, b)]
    isl = []
    for st, en in words(s['clip']):
        if en < a or st > b: continue
        st, en = max(st - 0.15, a), min(en + 0.25, b)
        if isl and st - isl[-1][1] < 0.55: isl[-1][1] = max(isl[-1][1], en)
        else: isl.append([st, en])
    isl = [x for x in isl if x[1] - x[0] > 0.25]
    return [tuple(x) for x in isl] or [(a, b)]

# ---------- timeline ----------
TL = []   # dicts: t0, dur, clip, a, b, speed, mode, sec, segi
t = 0.0
for si, S in enumerate(SECTIONS):
    for gi, s in enumerate(S['segs']):
        for a, b in pieces_for(s):
            dur = round((b - a) / s['speed'] * FPS) / FPS
            if dur < 0.2: continue
            TL.append(dict(t0=t, dur=dur, clip=s['clip'], a=a, b=b, speed=s['speed'], mode=s['mode'], sec=si, seg=s, n=len(TL)))
            t += dur
END_CARD = 3.0
TOTAL = t + END_CARD
print(f'pieces {len(TL)}  total {TOTAL/60:.1f} min')
for si, S in enumerate(SECTIONS):
    p = [x for x in TL if x['sec'] == si]
    print(f"  {S['name']:9s} {p[0]['t0']:6.1f}s  {sum(x['dur'] for x in p):5.1f}s")

def tl_time(seg, clip_t):
    """timeline time of a clip time inside seg (snaps forward over removed gaps)"""
    for p in TL:
        if p['seg'] is seg and clip_t <= p['b']:
            return p['t0'] + max(0, clip_t - p['a']) / p['speed']
    ps = [p for p in TL if p['seg'] is seg]; return ps[-1]['t0']

def seg_span(seg):
    ps = [p for p in TL if p['seg'] is seg]
    return ps[0]['t0'], ps[-1]['t0'] + ps[-1]['dur']

# ---------- render pieces ----------
def render_piece(p):
    out = f"{SEGDIR}/{p['n']:03d}.mp4"
    key = f"{p['clip']} {p['a']:.3f} {p['b']:.3f} {p['speed']} {p['mode']}"
    if os.path.exists(out) and open(out + '.key').read() == key: return out
    dur_in = p['b'] - p['a']
    vf = f"setpts=(PTS-STARTPTS)/{p['speed']},fps={FPS},scale={OW}:{OH}:flags=lanczos,format=yuv420p,eq=saturation=1.12:contrast=1.04"
    vol = {'sp': 1.0, 'act': 0.7, 'br': 0.25}[p['mode']]
    d = p['dur']
    cmd = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-ss', f"{p['a']:.3f}", '-t', f'{dur_in:.3f}', '-i', src(p['clip'])]
    if p['speed'] == 1.0:
        af = f'asetpts=PTS-STARTPTS,aresample=48000,aformat=channel_layouts=stereo,volume={vol},afade=in:d=0.03,afade=out:st={max(0, d-0.05):.3f}:d=0.05,apad'
        cmd += ['-vf', vf, '-af', af, '-map', '0:v:0', '-map', '0:a:0']
    else:
        cmd += ['-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=stereo', '-vf', vf, '-map', '0:v:0', '-map', '1:a:0']
    venc_seg = venc('45M', '4M')
    cmd += venc_seg + ['-c:a', 'aac', '-b:a', '192k', '-t', f'{d:.3f}', out]
    run(cmd); open(out + '.key', 'w').write(key)
    return out

def render_all():
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(3 if FINAL else 4) as ex: files = list(ex.map(render_piece, TL))
    end = f'{SEGDIR}/end.mp4'
    run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-f', 'lavfi', '-i', f'color=c=black:s={OW}x{OH}:r={FPS}:d={END_CARD}',
         '-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=stereo', '-t', str(END_CARD), '-pix_fmt', 'yuv420p'] +
        venc('10M', '1M') +
        ['-c:a', 'aac', '-b:a', '192k', end])
    with open(f'{SEGDIR}/list.txt', 'w') as f:
        for x in files + [end]: f.write(f"file '{os.path.abspath(x)}'\n")
    run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', f'{SEGDIR}/list.txt', '-c', 'copy', f'{SEGDIR}/joined.mp4'])

# ---------- garmin ----------
REC = json.load(open(f'{ROOT}/garmin/records.json')) if os.path.exists(f'{ROOT}/garmin/records.json') else []
RT = [r[0] for r in REC]
def garmin_at(real_s):
    if not REC: return None
    if real_s < RT[0] or real_s > RT[-1]: return None
    return REC[min(bisect.bisect_left(RT, real_s), len(REC) - 1)]
HAVE_GPS = bool(REC)
DMAX = REC[-1][3] if REC else 1; AMIN = min((r[2] for r in REC if r[2]), default=0); AMAX = max((r[2] for r in REC if r[2]), default=1)

# ---------- ASS ----------
def ts(x):
    x = max(0, x); h = int(x // 3600); m = int(x % 3600 // 60); s = x % 60
    return f'{h}:{m:02d}:{s:05.2f}'
F = 'Sukhumvit Set'
HEAD = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,Kanit,72,&H00FFFFFF,&H000000FF,&H00B45F1D,&H90000000,-1,0,0,0,100,100,0,0,1,7,3,2,60,60,70,1
Style: Call,Kanit,50,&H00FFFFFF,&H000000FF,&H00B45F1D,&H00000000,-1,-1,0,0,100,100,0,0,3,16,0,7,70,60,70,1
Style: Title,Kanit,124,&H00FFFFFF,&H000000FF,&H00B45F1D,&H90000000,-1,-1,0,0,100,100,0,0,1,6,4,4,110,60,60,1
Style: Sub,Kanit,54,&H00FFFFFF,&H000000FF,&H00B45F1D,&H90000000,-1,-1,0,0,100,100,1,0,1,4,2,4,115,60,60,1
Style: HUD,Kanit,46,&H00FFFFFF,&H000000FF,&H00B45F1D,&H90000000,-1,-1,0,0,100,100,0,0,1,4,1,9,60,60,46,1
Style: Draw,Kanit,20,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1
Style: Card,Kanit,60,&H00FFFFFF,&H000000FF,&H00B45F1D,&H00000000,-1,-1,0,0,100,100,0,0,1,0,0,7,0,0,0,1
Style: End,Kanit,84,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,-1,-1,0,0,100,100,0,0,1,0,0,5,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
EV = []
def ev(a, b, style, text, layer=0): EV.append(f'Dialogue: {layer},{ts(a)},{ts(b)},{style},,0,0,0,,{text}')

def poly(pts):
    return 'm ' + ' l '.join(f'{x:.0f} {y:.0f}' for x, y in pts)

def profile_path(x0, y0, w, h):
    step = max(1, len(REC) // 240)
    pts = [(x0 + r[3] / DMAX * w, y0 + h - (r[2] - AMIN) / (AMAX - AMIN) * h) for r in REC[::step] if r[2] and r[3] is not None]
    return pts

def route_path(x0, y0, size):
    g = [r for r in REC[::40] if r[4]]
    la = [r[4] for r in g]; lo = [r[5] for r in g]
    k = math.cos(math.radians(sum(la) / len(la)))
    sx = (max(lo) - min(lo)) * k; sy = max(la) - min(la); sc = size / max(sx, sy)
    return [(x0 + (r[5] - min(lo)) * k * sc, y0 + (max(la) - r[4]) * sc) for r in g]

EXTRA_SFX = []
BLING = []
def build_ass():
    EV.clear(); EXTRA_SFX.clear(); BLING.clear()
    # captions & callouts
    for S in SECTIONS:
        for s in S['segs']:
            a, b = seg_span(s)
            if s.get('cap'):
                c0 = tl_time(s, s['cap_at']) if 'cap_at' in s else a
                big = r'\fs110\frz4' if s.get('fx') == 'gauge' else ''
                ev(c0, min(b, c0 + 4.5), 'Cap', r'{\fad(120,200)' + big + r'\fscx80\fscy80\t(0,150,\fscx100\fscy100)}' + s['cap'], 5)
            if s.get('fx') == 'gauge':
                c0 = tl_time(s, s['cap_at'])
                # fuel gauge icon next to the caption: arc + needle swinging to F
                gx, gy = 1500, 905
                ev(c0, min(b, c0 + 4.5), 'Draw', r'{\fad(120,200)\an7\pos(0,0)\1c&HE8F1F4&\bord5\3c&HB45F1D&\p1}m %d %d b %d %d %d %d %d %d l %d %d{\p0}' % (gx-90, gy, gx-90, gy-120, gx+90, gy-120, gx+90, gy, gx-90, gy), 6)
                ev(c0, min(b, c0 + 4.5), 'HUD', r'{\fad(120,200)\an5\pos(%d,%d)\fs40\1c&H1D5FB4&\bord0\shad0}E{\fs40}               F' % (gx, gy - 20), 7)
                ev(c0, min(b, c0 + 4.5), 'Draw', r'{\fad(120,200)\an7\org(%d,%d)\pos(0,0)\1c&HB45F1D&\frz80\t(0,700,\frz-60)\p1}m %d %d l %d %d l %d %d l %d %d{\p0}' % (gx, gy-10, gx-5, gy-10, gx-3, gy-100, gx+3, gy-100, gx+5, gy-10), 8)
                ev(c0 + 0.7, min(b, c0 + 4.5), 'HUD', r'{\an5\pos(%d,%d)\fs44\1c&HFFFFFF&\3c&HB45F1D&\bord5\frz12\fscx150\fscy150\t(0,180,\fscx100\fscy100)}%s' % (gx + 110, gy - 120, s.get('gauge_text', 'FULL!')), 8)
            if s.get('fx') == 'stamp':
                c0 = tl_time(s, s['fx_at'])
                EXTRA_SFX.append(c0)
                ev(c0, c0 + 0.12, 'Draw', r'{\an7\pos(0,0)\1c&HFFFFFF&\1a&H40&\p1}m 0 0 l 1920 0 l 1920 1080 l 0 1080{\p0}', 9)
                ev(c0, c0 + 3.2, 'Draw', r'{\fad(0,300)\an7\pos(0,0)\1c&HB45F1D&\1a&H30&\p1}m 0 380 l 1920 300 l 1920 700 l 0 780{\p0}', 8)
                ev(c0, c0 + 3.2, 'Title', r'{\an5\pos(960,520)\fs230\1c&HFFFFFF&\3c&HB45F1D&\bord10\frz-6\fscx320\fscy320\t(0,160,\fscx92\fscy92)\t(160,260,\fscx100\fscy100)\fad(0,300)}' + s['stamp'], 9)
                ev(c0 + 0.35, c0 + 3.2, 'Sub', r'{\an5\pos(960,690)\fs62\1c&HE8F1F4&\frz-6\fad(150,300)}//// ' + s.get('stamp_sub', ''), 9)
            if s.get('bling'):
                t0b = tl_time(s, s['bling'])
                BLING.append((t0b, s))
                if s.get('bling_label'):
                    ev(t0b, t0b + s.get('bling_dur', 4.0), 'Call', r'{\fad(200,300)}//// ' + s['bling_label'], 5)
            if s.get('call'):
                ev(a + 0.3, min(b, a + 4.8), 'Call', r'{\fad(200,300)}//// ' + s['call'], 5)
            if s.get('title'):
                ev(a, b, 'Draw', r'{\fad(300,400)\an7\pos(0,0)\1c&HB45F1D&\1a&H70&\p1}m 0 0 l 1920 0 l 1920 1080 l 0 1080{\p0}', 3)
                ev(a, b, 'Draw', r'{\fad(300,400)\an7\pos(0,0)\1c&HB45F1D&\1a&H10&\p1}m 0 330 l 1250 330 l 1170 650 l 0 650{\p0}', 4)
                ev(a + 0.2, b, 'Title', r'{\fad(300,400)\pos(110,430)\an1}' + CFG['title'], 6)
                ev(a + 0.6, b, 'Sub', r'{\fad(300,400)\pos(115,525)\an1}//// ' + CFG['subtitle'], 6)
                ev(a + 0.9, b, 'Sub', r'{\fad(300,400)\pos(115,600)\an1\1c&HFFE8A6&}' + CFG['stats_line'], 6)
                rp = route_path(1300, 220, 520) if HAVE_GPS else []
                ev(a + 0.4, b, 'Draw', r'{\fad(300,400)\an7\pos(0,0)\bord6\3c&H000000&\1a&HFF&\p1}' + poly(rp + rp[::-1]) + r'{\p0}', 6)
                ev(a + 0.4, b, 'Draw', r'{\fad(300,400)\an7\pos(0,0)\bord3\3c&HFFFFFF&\1a&HFF&\p1}' + poly(rp + rp[::-1]) + r'{\p0}', 7)
            if s.get('card'):
                ev(a, b, 'Draw', r'{\fad(300,300)\an7\pos(0,0)\1c&HB45F1D&\1a&H38&\p1}m 0 0 l 1920 0 l 1920 1080 l 0 1080{\p0}', 3)
                lines = CFG['summary_lines']
                for i, L in enumerate(lines):
                    col = r'\1c&HE8A641&\fs84' if i == 0 else ''
                    ev(a + 0.2 + i * 0.25, b, 'Card', r'{\fad(250,300)\pos(140,%d)%s}%s' % (150 + i * 105, col, L), 6)
                pp = profile_path(1180, 640, 620, 240)
                ev(a + 0.5, b, 'Draw', r'{\fad(300,300)\an7\pos(0,0)\1c&HFFFFFF&\1a&H60&\p1}' + poly(pp + [(1800, 880), (1180, 880)]) + r'{\p0}', 6)
    # ---- HUD: cream "ink" panel, blue type (Pocari poster theme) ----
    CREAM, INK, SKYC = '&HE8F1F4&', '&HB45F1D&', '&HE8A641&'
    PX0, PY0, PW0, PH0 = 1440, 34, 446, 286           # panel box
    GX, GY, GW, GH = PX0 + 24, PY0 + 196, PW0 - 48, 66  # profile inside panel
    pp = profile_path(GX, GY, GW, GH)
    def box(x0, y0, x1, y1): return f'm {x0} {y0} l {x1} {y0} l {x1} {y1} l {x0} {y1}'
    def grade_at(i):
        d0 = REC[i][3] or 0
        j0 = i; j1 = i
        while j0 > 0 and (d0 - (REC[j0][3] or 0)) < 60: j0 -= 1
        while j1 < len(REC) - 1 and ((REC[j1][3] or 0) - d0) < 60: j1 += 1
        dd = (REC[j1][3] or 0) - (REC[j0][3] or 0)
        if dd < 30 or not REC[j1][2] or not REC[j0][2]: return 0
        return (REC[j1][2] - REC[j0][2]) / dd * 100
    for p in TL:
        if p['seg'].get('title') or p['seg'].get('card') or SECTIONS[p['sec']]['name'] in ('hook', 'montage', 'intro'): continue
        if garmin_at(cam_start(p['clip']) + p['a'] - OFFSET) is None: continue
        t0, t1 = p['t0'], p['t0'] + p['dur']
        ev(t0, t1, 'Draw', r'{\an7\pos(0,0)\1c' + INK + r'\1a&H30&\p1}' + box(PX0 + 8, PY0 + 8, PX0 + PW0 + 8, PY0 + PH0 + 8) + r'{\p0}', 0)
        ev(t0, t1, 'Draw', r'{\an7\pos(0,0)\1c' + CREAM + r'\bord3\3c' + INK + r'\p1}' + box(PX0, PY0, PX0 + PW0, PY0 + PH0) + r'{\p0}', 1)
        ev(t0, t1, 'Draw', r'{\an7\pos(0,0)\1c' + INK + r'\p1}' + box(PX0, PY0, PX0 + PW0, PY0 + 44) + r'{\p0}', 2)
        ev(t0, t1, 'HUD', r'{\an7\pos(%d,%d)\fs30\1c&HFFFFFF&\bord0\shad0}//// LIVE DATA · GARMIN' % (PX0 + 18, PY0 + 2), 3)
        ev(t0, t1, 'Draw', r'{\an7\pos(0,0)\1c' + INK + r'\1a&H40&\p1}' + poly(pp + [(GX + GW, GY + GH), (GX, GY + GH)]) + r'{\p0}', 2)
        k = 0.0
        while k < p['dur'] - 0.01:
            real = cam_start(p['clip']) + p['a'] + k * p['speed'] - OFFSET
            idx = bisect.bisect_left(RT, real)
            r = garmin_at(real)
            if r and r[1] and r[2]:
                a, b = t0 + k, t0 + min(p['dur'], k + 1.0)
                gr = grade_at(min(idx, len(REC) - 1))
                st = r'{\an7\pos(%d,%d)\fs54\1c' + INK + r'\bord0\shad0}%s{\fs28} %s'
                ev(a, b, 'HUD', st % (PX0 + 22, PY0 + 52, f'♥ {r[1]}', 'BPM'), 3)
                ev(a, b, 'HUD', st % (PX0 + 232, PY0 + 52, f'{gr:+.0f}%', 'ชัน'), 3)
                ev(a, b, 'HUD', st % (PX0 + 22, PY0 + 118, f'▲ {r[2]:,.0f}', 'M'), 3)
                ev(a, b, 'HUD', st % (PX0 + 232, PY0 + 118, f'{r[3]/1000 + PRESTART_KM:.1f}', 'KM'), 3)
                done = [q for q in pp if q[0] <= GX + r[3] / DMAX * GW]
                if len(done) > 1:
                    ev(a, b, 'Draw', r'{\an7\pos(0,0)\1c' + INK + r'\p1}' + poly(done + [(done[-1][0], GY + GH), (GX, GY + GH)]) + r'{\p0}', 3)
                dx = GX + r[3] / DMAX * GW; dy = GY + GH - (r[2] - AMIN) / (AMAX - AMIN) * GH
                ev(a, b, 'Draw', r'{\an7\pos(0,0)\1c' + SKYC + r'\bord3\3c' + CREAM + r'\p1}' + poly([(dx-8, dy-8), (dx+8, dy-8), (dx+8, dy+8), (dx-8, dy+8)]) + r'{\p0}', 4)
            k += 1.0
    # ---- chapter cards: cream band + mini route map with position ----
    CH = {S['name']: S['chapter'] for S in SECTIONS if S.get('chapter')}
    rp = route_path(0, 0, 1) if HAVE_GPS else []
    n = 0
    for si, S in enumerate(SECTIONS):
        if S['name'] not in CH: continue
        n += 1
        p = next(x for x in TL if x['sec'] == si)
        a, b = p['t0'], p['t0'] + min(3.2, sum(x['dur'] for x in TL if x['sec'] == si))
        real = cam_start(p['clip']) + p['a'] - OFFSET
        r = garmin_at(real) or REC[0]
        fx = r'\fad(250,300)'
        ev(a, b, 'Draw', r'{' + fx + r'\an7\pos(0,0)\1c' + CREAM + r'\bord3\3c' + INK + r'\p1}' + box(0, 812, 1100, 1010) + r'{\p0}', 6)
        ev(a, b, 'Draw', r'{' + fx + r'\an7\pos(0,0)\1c' + INK + r'\p1}' + box(0, 812, 300, 1010) + r'{\p0}', 7)
        ev(a, b, 'HUD', r'{%s\an7\pos(40,826)\fs40\1c&HFFFFFF&\bord0\shad0}CHAPTER\N{\fs110}%02d' % (fx, n), 8)
        ev(a, b, 'HUD', r'{%s\an7\pos(330,830)\fs92\1c%s\bord0\shad0}%s' % (fx, INK, CH[S['name']]), 8)
        ev(a, b, 'HUD', r'{%s\an7\pos(336,946)\fs40\1c%s\bord0\shad0}//// KM %.1f  ·  ▲ %s M' % (fx, INK, (r[3] or 0)/1000 + PRESTART_KM, f'{r[2]:,.0f}' if r[2] else '-'), 8)
        # mini route map
        mx, my, ms = 880, 830, 170
        pts = [(mx + x * ms, my + y * ms) for x, y in rp]
        ev(a, b, 'Draw', r'{' + fx + r'\an7\pos(0,0)\bord4\3c' + INK + r'\1a&HFF&\3a&H90&\p1}' + poly(pts + pts[::-1]) + r'{\p0}', 7)
        g = [x for x in REC[::40] if x[4]]
        cut = sum(1 for x in g if x[0] <= real)
        if cut > 1:
            dp = pts[:cut]
            ev(a, b, 'Draw', r'{' + fx + r'\an7\pos(0,0)\bord4\3c' + INK + r'\1a&HFF&\p1}' + poly(dp + dp[::-1]) + r'{\p0}', 8)
            x, y = dp[-1]
            ev(a, b, 'Draw', r'{' + fx + r'\an7\pos(0,0)\1c' + SKYC + r'\bord3\3c' + INK + r'\p1}' + poly([(x-10, y-10), (x+10, y-10), (x+10, y+10), (x-10, y+10)]) + r'{\p0}', 9)
    ev(TOTAL - END_CARD, TOTAL, 'Draw', r'{\an7\pos(0,0)\1c&HB45F1D&\p1}m 0 0 l 1920 0 l 1920 1080 l 0 1080{\p0}', 4)
    ev(TOTAL - END_CARD, TOTAL, 'End', r'{\fad(400,400)}ตัดต่อโดย Claude Code\N{\fs44\1c&HFFE8A6&}ถ่ายทำ · ตัดต่อ · เพลง · ข้อมูล Garmin', 5)
    txt = HEAD + '\n'.join(EV) + '\n'
    def bgr(h): h = h.lstrip('#'); return (h[4:6] + h[2:4] + h[0:2]).upper()
    T = CFG.get('theme', {})
    for default, key in (('B45F1D', 'primary'), ('E8F1F4', 'paper'), ('E8A641', 'accent'), ('FFE8A6', 'light')):
        if key in T: txt = txt.replace(default, bgr(T[key]))
    open(f'{SEGDIR}/vlog.ass', 'w').write(txt)

# ---------- music ----------
PROMPTS = {
 'metal_hook': 'explosive heavy metal intro for an adventure trail running vlog trailer, huge drum fill opening, fast double kick, chugging palm-muted riffs, epic and fun, 170 bpm, instrumental',
 'pop': 'light feel-good acoustic pop rock for the morning start of a trail running vlog with friends, ukulele and clean electric guitar, claps, playful and sunny, 112 bpm, instrumental',
 'rock': 'energetic upbeat indie rock for a rainy trail running adventure vlog, driving drums, punchy overdriven guitar riffs, catchy and fun, 150 bpm, instrumental',
 'pop2': 'scenic feel-good pop rock for mountain views and foggy villages in a travel vlog, shimmering clean guitars, steady groove, warm and relaxed, 108 bpm, instrumental',
 'light': 'light funny quirky acoustic background music for a lunch break scene in a travel vlog, pizzicato, whistling melody, bouncy, soft, 100 bpm, instrumental',
 'metal': 'heavy metal for an intense muddy downhill trail run in a bamboo forest, fast double kick drums, aggressive chugging riffs, energetic and fun, builds and drops, 172 bpm, instrumental',
 'rock_end': 'triumphant uplifting rock finale for the end of a trail running vlog, big drums, anthemic guitar melody, celebratory, ends with a clear final hit, 128 bpm, instrumental',
}
PROMPTS.update(CFG.get('music_prompts', {}))
def music_groups():
    groups = []
    for p in TL:
        cue = SECTIONS[p['sec']]['music']
        if cue is None: continue
        if groups and groups[-1][0] == cue and abs(groups[-1][1] + groups[-1][2] - p['t0']) < 0.01: groups[-1][2] += p['dur']
        else: groups.append([cue, p['t0'], p['dur']])
    if groups: groups[-1][2] += END_CARD
    return groups

def gen_music():
    import urllib.request
    key = os.environ['XI_KEY']
    need = {}
    for cue, st, ln in music_groups(): need[cue] = max(need.get(cue, 0), ln)
    from concurrent.futures import ThreadPoolExecutor
    def one(cue):
        path = f'{ROOT}/music/{cue}.mp3'
        ms = int(min(need[cue] + 4, 290) * 1000)
        if os.path.exists(path):
            have = float(run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', path]))
            if have * 1000 >= ms * 0.85: return cue, 'cached'
        body = json.dumps({'prompt': PROMPTS[cue], 'music_length_ms': ms, 'force_instrumental': True}).encode()
        req = urllib.request.Request('https://api.elevenlabs.io/v1/music', body, {'xi-api-key': key, 'Content-Type': 'application/json'})
        data = urllib.request.urlopen(req, timeout=600).read()
        open(path, 'wb').write(data)
        return cue, f'{ms/1000:.0f}s'
    with ThreadPoolExecutor(2) as ex:
        for r in ex.map(one, need): print('music', r)
    wh = f'{ROOT}/music/sfx_whoosh.mp3'
    if not os.path.exists(wh):
        body = json.dumps({'text': 'quick cinematic whoosh swoosh transition sound effect', 'duration_seconds': 1.2}).encode()
        req = urllib.request.Request('https://api.elevenlabs.io/v1/sound-generation', body, {'xi-api-key': key, 'Content-Type': 'application/json'})
        open(wh, 'wb').write(urllib.request.urlopen(req, timeout=120).read())

# ---------- final mix + burn ----------
def finish():
    groups = music_groups()
    ins = ['-i', f'{SEGDIR}/joined.mp4']
    fc = []
    def audible(path):
        out = subprocess.run(['ffmpeg', '-hide_banner', '-i', path, '-af', 'silencedetect=n=-45dB:d=0.5', '-f', 'null', '-'], capture_output=True, text=True).stderr
        dur = float(run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', path]))
        starts = [float(x.split('silence_start: ')[1].split()[0]) for x in out.splitlines() if 'silence_start' in x]
        return starts[-1] if starts and starts[-1] > dur - 6 else dur
    for i, (cue, st, ln) in enumerate(groups):
        path = f'{ROOT}/music/{cue}.mp3'
        aud = audible(path)
        tempo = f',atempo={max(0.88, aud / ln):.4f}' if aud < ln else ''
        ins += ['-i', path]
        fo = 2.5 if i == len(groups) - 1 else 1.2
        fc.append(f'[{i+1}:a]aresample=48000,aformat=channel_layouts=stereo{tempo},apad,atrim=0:{ln:.3f},afade=in:d=0.4,afade=out:st={max(0, ln-fo):.3f}:d={fo},adelay={int(st*1000)}:all=1[m{i}]')
    n = len(groups)
    fc.append(''.join(f'[m{i}]' for i in range(n)) + f'amix=inputs={n}:normalize=0,volume=0.55[mus]')
    fc.append('[0:a]asplit=2[dlg][key]')
    fc.append('[mus][key]sidechaincompress=threshold=0.015:ratio=12:attack=20:release=450:makeup=1[duck]')
    # whooshes at section changes
    starts = sorted({p['t0'] for p in TL if p is TL[0] or p['sec'] != TL[p['n'] - 1]['sec']} - {0.0})
    starts = sorted(starts + [t + 0.35 for t in EXTRA_SFX])
    ins += ['-i', f'{ROOT}/music/sfx_whoosh.mp3']
    wi = n + 1
    fc.append(f'[{wi}:a]aresample=48000,aformat=channel_layouts=stereo,volume=0.6,asplit={len(starts)}' + ''.join(f'[w{i}]' for i in range(len(starts))))
    for i, s0 in enumerate(starts): fc.append(f'[w{i}]adelay={int(max(0, s0-0.35)*1000)}:all=1[wd{i}]')
    fc.append('[dlg][duck]' + ''.join(f'[wd{i}]' for i in range(len(starts))) + f'amix=inputs={2+len(starts)}:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[aout]')
    vlab = '0:v'
    sc = OW / 1920
    def add_png(path, width, rot=None):
        nonlocal_ins.extend(['-loop', '1', '-framerate', str(FPS), '-t', f'{TOTAL:.3f}', '-i', path])
        idx = sum(1 for x in nonlocal_ins if x == '-i') - 1
        lab = f'png{idx}'
        r = f",rotate=a={rot}:c=none:ow=rotw(0.3):oh=roth(0.3)" if rot else ''
        fc.append(f'[{idx}:v]scale={int(width*sc)}:-1,format=rgba{r}[{lab}]')
        return lab
    nonlocal_ins = ins
    # ---- tracked bling (sunglasses + chain that follow a subject's head), see edl: bling=, track=
    for bi, (t0b, seg) in enumerate(BLING):
        DUR = seg.get('bling_dur', 4.0)
        K = []
        for ct, x, y in seg['track']:          # (clip_time, eye_x, eye_y) in 1920x1080 space
            tt = tl_time(seg, ct)
            if not K or tt > K[-1][0] + 0.05: K.append((tt, x, y))
        def lin(i):
            e = ''
            for (t1, x1, y1), (t2, x2, y2) in zip(K, K[1:]):
                v1, v2 = (x1, x2) if i == 0 else (y1, y2)
                e += f'if(between(t,{t1:.3f},{t2:.3f}),{v1}+({v2}-{v1})*(t-{t1:.3f})/{t2-t1:.3f},'
            return e + f'{K[-1][1+i]}' + ')' * (len(K) - 1)
        X, Y = lin(0), lin(1)
        gl = add_png(f'{ROOT}/sprites/glasses.png', seg.get('glasses_w', 150))
        ch = add_png(f'{ROOT}/sprites/chain.png', seg.get('chain_w', 130))
        drop = f'(-300*(1-min(1,(t-{t0b:.3f})/0.45)))'
        fc.append(f"[{vlab}][{gl}]overlay=x='({X}-{seg.get('glasses_w',150)/2})*{sc}':y='({Y}-18+{drop})*{sc}':enable='between(t,{t0b:.3f},{t0b+DUR:.3f})':eof_action=pass[bl{bi}a]")
        fc.append(f"[bl{bi}a][{ch}]overlay=x='({X}-95)*{sc}':y='({Y}+40)*{sc}':enable='between(t,{t0b+0.55:.3f},{t0b+DUR:.3f})':eof_action=pass[bl{bi}b]")
        vlab = f'bl{bi}b'
    # ---- stickers from project.json: [{file, t0, t1, x, y, w, anim: bounce|slide|none, wobble}]
    for si, st in enumerate(CFG.get('stickers', [])):
        rot = f"{st.get('wobble', 0.1)}*sin(2*PI*t*1.8)" if st.get('wobble', 0.1) else None
        lab = add_png(f"{ROOT}/sprites/{st['file']}", st.get('w', 300), rot)
        t0s, t1s = st['t0'], st['t1']
        dx = dy = '0'
        if st.get('anim', 'bounce') == 'bounce': dy = f'(1-min(1,(t-{t0s})/0.35))*400'
        elif st['anim'] == 'slide': dx = f'(1-min(1,(t-{t0s})/0.4))*700'
        fc.append(f"[{vlab}][{lab}]overlay=x='{st.get('x',1520)*sc:.0f}-w/2+({dx})*{sc:.3f}':y='{st.get('y',560)*sc:.0f}-h/2+({dy})*{sc:.3f}':enable='between(t,{t0s},{t1s})':eof_action=pass[st{si}]")
        vlab = f'st{si}'
    fc.append(f"[{vlab}]ass={SEGDIR}/vlog.ass:fontsdir={ROOT}/fonts[vout]")
    out = f"{ROOT}/output/{CFG.get('output_name', 'trail_vlog')}_{MODE}.mp4"
    os.makedirs(f'{ROOT}/output', exist_ok=True)
    venc_out = venc('40M', '4M')
    run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y'] + ins + ['-filter_complex', ';'.join(fc), '-map', '[vout]', '-map', '[aout]'] + venc_out +
        ['-c:a', 'aac', '-b:a', '256k', '-movflags', '+faststart', out])
    print('wrote', out)

if __name__ == '__main__':
    if '--plan' in sys.argv: sys.exit(0)
    gen_music()
    render_all()
    build_ass()
    finish()
