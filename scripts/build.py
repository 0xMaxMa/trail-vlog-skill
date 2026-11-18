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
    for attempt in range(2):                 # hardware encoder can hang (e.g. after sleep): time out and retry once
        try: r = subprocess.run(cmd, capture_output=True, text=True, timeout=1800); break
        except subprocess.TimeoutExpired:
            print('timeout, retrying:', ' '.join(cmd)[:200], flush=True)
    else: sys.exit('ffmpeg hung twice')
    if r.returncode: print(' '.join(cmd)); print(r.stderr[-2000:]); sys.exit(1)
    return r.stdout

EXTRA = CFG.get('extra_clips', {})          # {'pv1': 'Photo/video/x.mov'} — other cameras (e.g. event photographers)
def raw_path(c):
    if c in EXTRA: return os.path.join(ROOT, EXTRA[c])
    vids = [p for p in (glob.glob(f'{ROOT}/raw/*_{c}_*.*') or glob.glob(f'{ROOT}/raw/{c}.*')) if p.lower().endswith(('.mp4', '.mov'))]
    return sorted(vids, key=lambda p: ('_' + c + '_') not in os.path.basename(p))[0]
def src(c):
    if FINAL: return raw_path(c)
    if c in EXTRA and not os.path.exists(f'proxy/{c}.mp4'):   # extra clips were not ingested: make a proxy (keeps aspect)
        run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-i', raw_path(c), '-vf', 'fps=30,scale=-2:540'] +
            (['-c:v', 'h264_videotoolbox', '-b:v', '3M'] if sys.platform == 'darwin' else ['-c:v', 'libx264', '-preset', 'veryfast']) +
            ['-c:a', 'aac', '-ar', '48000', '-ac', '2', f'proxy/{c}.mp4'])
    return f'proxy/{c}.mp4'
_PROBE = {}
def probe(c):
    """(width, height, has_audio) of a clip's source"""
    if c not in _PROBE:
        o = run(['ffprobe', '-v', 'error', '-show_entries', 'stream=codec_type,width,height', '-of', 'json', raw_path(c)])
        st = json.loads(o)['streams']; v = next(x for x in st if x['codec_type'] == 'video')
        _PROBE[c] = (v['width'], v['height'], any(x['codec_type'] == 'audio' for x in st))
    return _PROBE[c]
def _day0():
    """date (YYYYMMDD) that second 0 refers to: project.json day0, else the earliest DJI file date"""
    if CFG.get('day0'): return str(CFG['day0'])
    ds = sorted(os.path.basename(p).split('_')[1][:8] for p in glob.glob(f'{ROOT}/raw/DJI_*'))
    return ds[0] if ds else None
DAY0 = _day0()
def cam_start(c):
    """Local wall-clock seconds since midnight of DAY0 when the clip started (camera clock, before OFFSET correction).
    Keeps counting past 86400 for clips filmed after midnight (matches garmin/records.json)."""
    name = os.path.basename(raw_path(c))
    if name.startswith('DJI_') and len(name.split('_')[1]) >= 14:
        import datetime as _dt
        ymd, hms = name.split('_')[1][:8], name.split('_')[1][8:14]
        days = (_dt.date(int(ymd[:4]), int(ymd[4:6]), int(ymd[6:8])) - _dt.date(int(DAY0[:4]), int(DAY0[4:6]), int(DAY0[6:8]))).days if DAY0 else 0
        return days * 86400 + int(hms[:2]) * 3600 + int(hms[2:4]) * 60 + int(hms[4:6])
    ct = run(['ffprobe', '-v', 'error', '-show_entries', 'format_tags=creation_time', '-of', 'csv=p=0', raw_path(c)]).strip()
    import datetime as _dt
    t = _dt.datetime.fromisoformat(ct.replace('Z', '+00:00')) + _dt.timedelta(hours=CFG.get('utc_offset_h', 7))
    return t.hour * 3600 + t.minute * 60 + t.second

# ---------- speech tightening ----------
SKIP_EV = ('เดิน', 'วิ่ง', 'ฝน', 'น้ำ', 'ดนตรี', 'มอเตอร์', 'ไก่', 'ถุงมือ', 'พูดแทรก', 'คุย', 'ไอ', 'หอบ', 'หายใจ', 'ออกแรง', 'ประตู', 'รถ', 'ตบ', 'ล้ม', 'ดื่ม')
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

PHRASE_GAP = CFG.get('phrase_gap', 0.9)    # a pause shorter than this is inside a sentence
def snap_segments():
    """Never cut someone mid-sentence: move each speech segment's in-point back to where the phrase starts and its
    out-point forward to where it ends (STT word times), without overlapping the neighbouring segment of the same clip.
    Per segment: snap=False to disable, hard_a / hard_b to keep one edge exactly, max_back / max_fwd to limit (s). Original bounds kept as a0/b0."""
    segs = [s for S in SECTIONS for s in S['segs']]
    for i, s in enumerate(segs):
        if s['mode'] not in ('sp', 'act') or s.get('snap') is False or s['clip'] in EXTRA: continue
        try: ws = sorted(words(s['clip']))
        except IndexError: continue
        s['a0'], s['b0'] = s['a'], s['b']
        lo = max([o['b'] for o in segs if o is not s and o['clip'] == s['clip'] and o['b'] <= s['a'] + 0.01] or [0.0])
        hi = min([o['a'] for o in segs if o is not s and o['clip'] == s['clip'] and o['a'] >= s['b'] - 0.01] or [1e9])
        a, b = s['a'], s['b']
        # back: a word straddles a, or ends just before it -> walk to the phrase start
        MB, MF = s.get('max_back', 3.0), s.get('max_fwd', 3.5)
        prev = [w for w in ws if w[0] < a]
        if prev and prev[-1][1] > a - PHRASE_GAP and not s.get('hard_a'):
            j = len(prev) - 1
            while j > 0 and ws[j][0] - ws[j - 1][1] < PHRASE_GAP and ws[j - 1][0] > a - MB: j -= 1
            if j > 0 and ws[j][0] - ws[j - 1][1] < PHRASE_GAP:      # phrase runs on past the limit: start at the widest pause inside it
                cand = [q for q in range(1, len(prev)) if ws[q - 1][0] > a - MB - 0.01 or q == len(prev) - 1]
                j = max(cand, key=lambda q: ws[q][0] - ws[q - 1][1]) if cand else len(prev) - 1
            a = max(ws[j][0] - 0.2, lo)
        # forward: a word straddles b, or starts just after it -> walk to the phrase end
        nxt = [k for k, w in enumerate(ws) if w[1] > b]
        if nxt and ws[nxt[0]][0] < b + PHRASE_GAP and not s.get('hard_b'):
            k = nxt[0]
            while k < len(ws) - 1 and ws[k + 1][0] - ws[k][1] < PHRASE_GAP and ws[k + 1][1] < b + MF: k += 1
            if k < len(ws) - 1 and ws[k + 1][0] - ws[k][1] < PHRASE_GAP:     # runs on: end at the widest pause within reach
                cand = [q for q in range(nxt[0], k + 1)]
                k = max(cand, key=lambda q: ws[q + 1][0] - ws[q][1])
            b = min(ws[k][1] + 0.4, hi)
        s['a'], s['b'] = round(min(a, s['a']), 2), round(max(b, s['b']), 2)
snap_segments()

def pieces_for(s):
    a, b = s['a'], s['b']
    if s['mode'] == 'ph': return [(0.0, s['b'])]
    if s['mode'] != 'sp' or s.get('tight') is False: return [(a, b)]
    isl = []      # speech islands; only pauses longer than ~1.2 s are tightened (to ~0.6 s)
    for st, en in words(s['clip']):
        if en < a or st > b: continue
        st, en = max(st - 0.25, a), min(en + 0.35, b)
        if isl and st - isl[-1][1] < 0.45: isl[-1][1] = max(isl[-1][1], en)
        else: isl.append([st, en])
    isl = [x for x in isl if x[1] - x[0] > 0.3]
    if isl: isl[0][0] = a if isl[0][0] - a < 0.8 else isl[0][0]; isl[-1][1] = b if b - isl[-1][1] < 1.0 else isl[-1][1]
    return [tuple(x) for x in isl] or [(a, b)]

# ---------- timeline ----------
TL = []   # dicts: t0, dur, clip, a, b, speed, mode, sec, segi
t = 0.0
for si, S in enumerate(SECTIONS):
    for gi, s in enumerate(S['segs']):
        for a, b in pieces_for(s):
            dur = round((b - a) / s['speed'] * FPS) / FPS
            if dur < 0.2: continue
            TL.append(dict(t0=t, dur=dur, clip=s['clip'], a=a, b=b, speed=s['speed'], mode=s['mode'], sec=si, seg=s, n=len(TL), freeze=0))
            t += dur
        if s.get('freeze') and TL and TL[-1]['seg'] is s:     # hold the last frame (e.g. before a shutter -> photo cut)
            TL[-1]['freeze'] = s['freeze']; TL[-1]['dur'] += s['freeze']; t += s['freeze']
END_CARD = 3.0 if CFG.get('end_card', True) else 0.0     # project.json end_card: false -> the video just ends
TOTAL = t + END_CARD
print(f'pieces {len(TL)}  total {TOTAL/60:.1f} min')
for si, S in enumerate(SECTIONS):
    p = [x for x in TL if x['sec'] == si]
    print(f"  {S['name']:12s} {int(p[0]['t0']//60)}:{p[0]['t0']%60:04.1f}  {sum(x['dur'] for x in p):5.1f}s")

def real_at(p, k=0.0):
    """real local time (s since DAY0 midnight) at k seconds into timeline piece p.
    Segments may carry real=<s> (photos, other cameras): the real time at the segment's in-point."""
    s = p['seg']
    if 'real' in s: return s['real'] + (p['a'] - s['a']) + k * p['speed']
    return cam_start(p['clip']) + p['a'] + k * p['speed'] - OFFSET

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
KB = {   # Ken Burns moves: (zoom_from, zoom_to, pan_x_from, pan_x_to, pan_y_from, pan_y_to); pan in fraction of the spare margin
    'in': (1.0, 1.12, 0, 0, 0, 0), 'out': (1.12, 1.0, 0, 0, 0, 0), 'left': (1.1, 1.1, 1, -1, 0, 0), 'right': (1.1, 1.1, -1, 1, 0, 0),
    'up': (1.1, 1.1, 0, 0, 1, -1), 'down': (1.1, 1.1, 0, 0, -1, 1), 'in_left': (1.0, 1.14, 0, -0.8, 0, 0), 'in_right': (1.0, 1.14, 0, 0.8, 0, 0),
    'in_up': (1.0, 1.14, 0, 0, 0, -0.8), 'none': (1.0, 1.0, 0, 0, 0, 0)}
def photo_canvas(path, fy=0.42, bright=1.0):
    """16:9 canvas with 20 % headroom: landscape photos are cover-cropped (fy = vertical focus 0..1),
    portrait ones sit on a blurred, darkened copy of themselves (the standard 9:16-in-16:9 fill)."""
    from PIL import Image, ImageFilter, ImageOps, ImageEnhance
    im = ImageOps.exif_transpose(Image.open(path)).convert('RGB')
    if bright != 1.0: im = ImageEnhance.Brightness(im).enhance(bright)
    cw, ch = int(OW * 1.2), int(OH * 1.2)
    def cover(img, w, h, fy):
        sc = max(w / img.width, h / img.height); img = img.resize((max(w, round(img.width * sc)), max(h, round(img.height * sc))), Image.LANCZOS)
        x0 = (img.width - w) // 2; y0 = int((img.height - h) * fy); return img.crop((x0, y0, x0 + w, y0 + h))
    if im.width / im.height >= 1.3: return cover(im, cw, ch, fy)
    bg = cover(im.resize((im.width // 8, im.height // 8)), cw // 8, ch // 8, 0.5).filter(ImageFilter.GaussianBlur(6)).resize((cw, ch), Image.BICUBIC)
    bg = ImageEnhance.Brightness(bg).enhance(0.55)
    fh = ch; fw = round(im.width * fh / im.height); bg.paste(im.resize((fw, fh), Image.LANCZOS), ((cw - fw) // 2, 0)); return bg

def render_photo(p, out):
    from PIL import Image
    s = p['seg']; d = p['dur']; n = max(1, round(d * FPS))
    C = photo_canvas(os.path.join(ROOT, s['photo']), s.get('fy', 0.42), s.get('bright', 1.0)); cw, ch = C.size
    z0, z1, x0, x1, y0, y1 = KB[s.get('kb', 'in')]
    ff = subprocess.Popen(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{OW}x{OH}', '-r', str(FPS), '-i', '-',
                           '-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=stereo', '-map', '0:v', '-map', '1:a', '-pix_fmt', 'yuv420p'] + venc('45M', '4M') +
                          ['-c:a', 'aac', '-b:a', '192k', '-t', f'{d:.3f}', out], stdin=subprocess.PIPE)
    for i in range(n):
        u = i / max(1, n - 1); u = u * u * (3 - 2 * u) * 0.35 + u * 0.65          # gentle ease
        z = z0 + (z1 - z0) * u
        vw, vh = cw / 1.2 / z, ch / 1.2 / z               # view rect in canvas px (z=1 -> centre 1/1.2 of the canvas)
        mx, my = (cw - vw) / 2, (ch - vh) / 2
        cx = cw / 2 + mx * (x0 + (x1 - x0) * u); cy = ch / 2 + my * (y0 + (y1 - y0) * u)
        fr = C.transform((OW, OH), Image.AFFINE, (vw / OW, 0, cx - vw / 2, 0, vh / OH, cy - vh / 2), resample=Image.BICUBIC)
        ff.stdin.write(fr.tobytes())
    ff.stdin.close(); ff.wait()
    if ff.returncode: sys.exit(f'photo render failed: {s["photo"]}')

SPEECH_LUFS = CFG.get('speech_lufs', -19.0)
_GAIN = {}
def speech_gain(s, clip):
    """dB that brings this segment's talking to SPEECH_LUFS (gated loudness of the speech islands; capped)"""
    k = (clip, s['a'], s['b'])
    if k not in _GAIN:
        isl = pieces_for(s) if s['mode'] == 'sp' else [(s['a'], s['b'])]
        sel = '+'.join(f'between(t,{a:.2f},{b:.2f})' for a, b in isl)
        o = subprocess.run(['ffmpeg', '-hide_banner', '-nostats', '-ss', f"{s['a']:.3f}", '-t', f"{s['b'] - s['a']:.3f}", '-i', src(clip), '-vn',
                            '-af', f"asetpts=PTS-STARTPTS+{s['a']:.3f}/TB,aselect='{sel}',ebur128=framelog=quiet", '-f', 'null', '-'],
                           capture_output=True, text=True).stderr
        try: I = float(o.rsplit('I:', 1)[1].split('LUFS')[0])
        except (IndexError, ValueError): I = SPEECH_LUFS
        _GAIN[k] = max(-6.0, min(14.0, SPEECH_LUFS - I)) if I > -70 else 0.0
    return _GAIN[k]

def render_piece(p):
    out = f"{SEGDIR}/{p['n']:03d}.mp4"
    s = p['seg']
    key = f"{p['clip']} {p['a']:.3f} {p['b']:.3f} {p['speed']} {p['mode']} {p['freeze']} v2 {s.get('vol')}" + (f" {s['photo']} {s.get('kb')} {s.get('fy')} {s.get('bright')} {p['dur']:.3f}" if p['mode'] == 'ph' else '')
    if os.path.exists(out + '.key') and os.path.exists(out) and open(out + '.key').read() == key: return out
    if p['mode'] == 'ph':
        render_photo(p, out); open(out + '.key', 'w').write(key); return out
    dur_in = p['b'] - p['a']
    w, h, has_a = probe(p['clip'])
    look = 'eq=saturation=1.12:contrast=1.04' + (f",eq=brightness={s['lift']}" if s.get('lift') else '')
    if w / h < 1.3:   # portrait / square source: blurred fill behind the centred clip
        vf = (f"setpts=(PTS-STARTPTS)/{p['speed']},fps={FPS},split[a][b];[a]scale={OW//8}:{OH//8}:force_original_aspect_ratio=increase,crop={OW//8}:{OH//8},"
              f"gblur=sigma=6,eq=brightness=-0.18,scale={OW}:{OH}[bg];[b]scale=-2:{OH}:flags=lanczos[fg];[bg][fg]overlay=(W-w)/2:0,format=yuv420p,{look}")
    else:
        vf = f"setpts=(PTS-STARTPTS)/{p['speed']},fps={FPS},scale={OW}:{OH}:flags=lanczos,format=yuv420p,{look}"
    if p['freeze']: vf += f",tpad=stop_mode=clone:stop_duration={p['freeze']:.3f}"
    vol = {'sp': 1.0, 'act': 0.7, 'br': 0.25}[p['mode']] * s.get('vol', 1.0)
    voice = ''
    if p['mode'] in ('sp', 'act') and has_a and p['speed'] == 1.0:     # level quiet talkers up to a common loudness
        g_db = speech_gain(s, p['clip'])
        vol = s.get('vol', 1.0) * (0.85 if p['mode'] == 'act' else 1.0)
        voice = f'highpass=f=85,volume={g_db:.1f}dB,alimiter=limit=0.9:level=disabled,'
    d = p['dur']
    cmd = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-ss', f"{p['a']:.3f}", '-t', f'{dur_in:.3f}', '-i', src(p['clip'])]
    if p['speed'] == 1.0 and has_a:
        af = f'asetpts=PTS-STARTPTS,aresample=48000,aformat=channel_layouts=stereo,{voice}volume={vol},afade=in:d=0.03,afade=out:st={max(0, d-0.05):.3f}:d=0.05,apad'
        if p['freeze']:   # -af + apad next to tpad hangs hevc_videotoolbox: keep audio in the graph with a fixed pad length
            cmd += ['-filter_complex', f'[0:v:0]{vf}[v];[0:a:0]{af}=whole_dur={d:.3f}[a]', '-map', '[v]', '-map', '[a]']
        else:
            cmd += ['-filter_complex', f'[0:v:0]{vf}[v]', '-af', af, '-map', '[v]', '-map', '0:a:0']
    else:
        cmd += ['-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=stereo', '-filter_complex', f'[0:v:0]{vf}[v]', '-map', '[v]', '-map', '1:a:0']
    venc_seg = venc('45M', '4M')
    cmd += venc_seg + ['-c:a', 'aac', '-b:a', '192k', '-t', f'{d:.3f}', out]
    run(cmd); open(out + '.key', 'w').write(key)
    return out

def render_all():
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(3 if FINAL else 4) as ex: files = list(ex.map(render_piece, TL))
    end = f'{SEGDIR}/end.mp4'
    if END_CARD: run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-f', 'lavfi', '-i', f'color=c=black:s={OW}x{OH}:r={FPS}:d={END_CARD}',
         '-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=stereo', '-t', str(END_CARD), '-pix_fmt', 'yuv420p'] +
        venc('10M', '1M') +
        ['-c:a', 'aac', '-b:a', '192k', end])
    with open(f'{SEGDIR}/list.txt', 'w') as f:
        for x in files + ([end] if END_CARD else []): f.write(f"file '{os.path.abspath(x)}'\n")
    run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', f'{SEGDIR}/list.txt', '-c', 'copy', f'{SEGDIR}/joined.mp4'])

# ---------- garmin ----------
REC = json.load(open(f'{ROOT}/garmin/records.json')) if os.path.exists(f'{ROOT}/garmin/records.json') else []
RT = [r[0] for r in REC]
def garmin_at(real_s):
    if not REC: return None
    if real_s < RT[0] or real_s > RT[-1]: return None
    return REC[min(bisect.bisect_left(RT, real_s), len(REC) - 1)]
HAVE_GPS = bool(REC)
def _hms(x): h, m, *sec = map(int, x.split(':')); return h * 3600 + m * 60 + (sec[0] if sec else 0)
STN = [dict(code=c, name=nm, km=km, real=_hms(t)) for c, nm, km, t in CFG.get('stations', [])]   # [code, name, km, 'HH:MM:SS' (>24h after midnight)]
for st in STN:      # where the station sits on the watch's own distance axis (watch km drifts from official km)
    r = garmin_at(st['real']); st['wkm'] = (r[3] if r and r[3] is not None else st['km'] * 1000)
def leg_at(real):
    """(last station passed, next station) at a real time"""
    if not STN: return None, None
    prev = [x for x in STN if x['real'] <= real + 60]
    nxt = [x for x in STN if x['real'] > real + 60]
    return (prev[-1] if prev else None), (nxt[0] if nxt else None)
def gain_between(d0, d1):
    """total climb (m) on the watch between two distances, smoothed over 50 m steps"""
    up = 0.0; last = None
    for r in REC:
        if r[3] is None or not r[2] or r[3] < d0: continue
        if r[3] > d1: break
        if last is None or r[3] - last[0] >= 50:
            if last is not None and r[2] > last[1]: up += r[2] - last[1]
            last = (r[3], r[2])
    return up
def stn(code): return next(x for x in STN if x['code'] == code)
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

def circ(x, y, r):
    k = 0.5523 * r
    return (f'm {x:.0f} {y - r:.0f} b {x + k:.0f} {y - r:.0f} {x + r:.0f} {y - k:.0f} {x + r:.0f} {y:.0f} b {x + r:.0f} {y + k:.0f} {x + k:.0f} {y + r:.0f} {x:.0f} {y + r:.0f} '
            f'b {x - k:.0f} {y + r:.0f} {x - r:.0f} {y + k:.0f} {x - r:.0f} {y:.0f} b {x - r:.0f} {y - k:.0f} {x - k:.0f} {y - r:.0f} {x:.0f} {y - r:.0f}')

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
SHUTTER = []
BLING = []
def hhmm(real): real %= 86400; return f'{int(real // 3600):02d}:{int(real % 3600 // 60):02d}'
CARDS = []     # (t0, t1) of station/climb cards: the HUD hides while they are up
CREAM_, INK_, SKY_ = '&HE8F1F4&', '&HB45F1D&', '&HE8A641&'
def _box(x0, y0, x1, y1): return f'm {x0:.0f} {y0:.0f} l {x1:.0f} {y0:.0f} l {x1:.0f} {y1:.0f} l {x0:.0f} {y1:.0f}'
def _prof(d0, d1, x0, y0, w, h, a0=None, a1=None, dom=None):
    """profile polygon (closed to the baseline) for watch distance d0..d1 mapped into a box whose x axis spans dom (default d0..d1)"""
    xs = [r for r in REC if r[2] and r[3] is not None and d0 <= r[3] <= d1]
    xs = xs[::max(1, len(xs) // 400)]
    lo = a0 if a0 is not None else min(r[2] for r in xs); hi = a1 if a1 is not None else max(r[2] for r in xs)
    m0, m1 = dom or (d0, d1)
    X = lambda d: x0 + (d - m0) / (m1 - m0) * w
    Y = lambda e: y0 + h - (e - lo) / max(1, hi - lo) * h
    pts = [(X(r[3]), Y(r[2])) for r in xs]
    return pts + [(X(xs[-1][3]), y0 + h), (X(xs[0][3]), y0 + h)], X, Y

def station_card(s):
    """lower panel on arrival at a station: whole-course profile, stations, where we are, what the next leg climbs"""
    a, b = seg_span(s); c0 = a + s.get('st_at', 0.4); c1 = c0 + s.get('st_dur', CFG.get('station_card_dur', 8.5))
    if s.get('st'):
        here = stn(s['st']); i = STN.index(here); nx = STN[i + 1] if i + 1 < len(STN) else None
    else:       # where='text': a "you are here" card at this moment of the race (not a station)
        p0 = next(p for p in TL if p['seg'] is s); real = real_at(p0); r0 = garmin_at(real)
        here = dict(code='', name=s['where'], km=round(r0[3] / 1000, 1), real=real, wkm=r0[3]); i = 1
        nx = leg_at(real)[1]
    CARDS.append((c0, c1))
    fx = r'\fad(250,350)'
    X0, Y0, X1, Y1 = 70, 560, 1850, 1030
    ev(c0, c1, 'Draw', r'{' + fx + r'\an7\pos(0,0)\1c' + INK_ + r'\1a&H40&\p1}' + _box(X0 + 10, Y0 + 10, X1 + 10, Y1 + 10) + r'{\p0}', 10)
    ev(c0, c1, 'Draw', r'{' + fx + r'\an7\pos(0,0)\1c' + CREAM_ + r'\bord3\3c' + INK_ + r'\p1}' + _box(X0, Y0, X1, Y1) + r'{\p0}', 11)
    ev(c0, c1, 'Draw', r'{' + fx + r'\an7\pos(0,0)\1c' + INK_ + r'\p1}' + _box(X0, Y0, X1, Y0 + 70) + r'{\p0}', 12)
    el = here['real'] - STN[0]['real']
    r = garmin_at(here['real'])
    head = f"//// {hhmm(here['real'])}  {here['name']}  ·  KM {here['km']:g}" if not here['code'] else f"//// {hhmm(here['real'])}  ถึง {here['code']} {here['name']}  ·  {here['km']:g} KM"
    ev(c0, c1, 'HUD', r'{%s\an7\pos(%d,%d)\fs48\1c&HFFFFFF&\bord0\shad0}%s' % (fx, X0 + 26, Y0 + 6, head), 13)
    pct = here['km'] / STN[-1]['km'] * 100
    ev(c0, c1, 'HUD', r'{%s\an9\pos(%d,%d)\fs48\1c%s\bord0\shad0}%d%%' % (fx, X1 - 26, Y0 + 6, SKY_, pct), 13)
    # profile
    PX, PY, PW, PH = X0 + 60, Y0 + 96, X1 - X0 - 120, 200
    full, X, Y = _prof(0, DMAX, PX, PY, PW, PH, AMIN, AMAX)
    ev(c0, c1, 'Draw', r'{' + fx + r'\an7\pos(0,0)\1c' + INK_ + r'\1a&HB0&\p1}' + poly(full) + r'{\p0}', 12)
    done, _, _ = _prof(0, here['wkm'], PX, PY, PW, PH, AMIN, AMAX, dom=(0, DMAX))
    ev(c0, c1, 'Draw', r'{' + fx + r'\an7\pos(0,0)\1c' + INK_ + r'\1a&H10&\p1}' + poly(done) + r'{\p0}', 13)
    if nx:   # next leg sweeps in, in the accent colour
        leg, _, _ = _prof(here['wkm'], nx['wkm'], PX, PY, PW, PH, AMIN, AMAX, dom=(0, DMAX))
        xa, xb = X(here['wkm']), X(nx['wkm'])
        ev(c0 + 0.6, c1, 'Draw', r'{\fad(0,350)\an7\pos(0,0)\clip(%d,%d,%d,%d)\t(0,900,\clip(%d,%d,%d,%d))\1c%s\p1}%s{\p0}' % (xa, PY - 20, xa + 1, PY + PH + 2, xa, PY - 20, xb, PY + PH + 2, SKY_, poly(leg)), 13)
    for st in STN:     # station ticks + codes
        x = X(st['wkm']); col = INK_ if st['real'] <= here['real'] else '&H9A8A70&'
        ev(c0, c1, 'Draw', r'{' + fx + r'\an7\pos(0,0)\1c' + col + r'\p1}' + _box(x - 1.5, PY - 6, x + 1.5, PY + PH) + r'{\p0}', 14)
        ev(c0, c1, 'HUD', r'{%s\an8\pos(%d,%d)\fs27\1c%s\bord0\shad0}%s\N{\fs22}%gkm' % (fx, x, PY + PH + 4, col, st['code'], st['km']), 14)
    x, y = X(here['wkm']), Y(r[2] if r and r[2] else AMIN)
    ev(c0, c1, 'HUD', r'{%s\an2\pos(%d,%d)\fs34\1c%s\3c%s\bord5\shad0}อยู่ตรงนี้\N▼' % (fx, max(x, PX + 40), y + 2, INK_, CREAM_), 15)
    if nx:
        msg = f"ถัดไป → {nx['code']} {nx['name']}"
    else:
        msg = CFG.get('stats_line', '')
    ev(c0 + 0.6, c1, 'HUD', r'{\fad(250,350)\an1\pos(%d,%d)\fs40\1c%s\bord0\shad0}%s' % (X0 + 30, Y1 - 18, INK_, msg), 14)

def boss_card(s):
    """lower panel: whole-course profile, where we are now, and a named section ahead highlighted (boss=(km0, km1, name, tag))"""
    k0, k1, name, tag = s['boss']
    a, b = seg_span(s); c0 = tl_time(s, s['boss_at']) if 'boss_at' in s else a + 0.3; c1 = c0 + s.get('boss_dur', 8.0); CARDS.append((c0, c1))
    p0 = next(p for p in TL if p['seg'] is s); r0 = garmin_at(real_at(p0))
    fx = r'\fad(250,350)'
    X0, Y0, X1, Y1 = 70, 560, 1850, 1030
    ev(c0, c1, 'Draw', r'{' + fx + r'\an7\pos(0,0)\1c' + INK_ + r'\1a&H40&\p1}' + _box(X0 + 10, Y0 + 10, X1 + 10, Y1 + 10) + r'{\p0}', 10)
    ev(c0, c1, 'Draw', r'{' + fx + r'\an7\pos(0,0)\1c' + CREAM_ + r'\bord3\3c' + INK_ + r'\p1}' + _box(X0, Y0, X1, Y1) + r'{\p0}', 11)
    ev(c0, c1, 'Draw', r'{' + fx + r'\an7\pos(0,0)\1c' + INK_ + r'\p1}' + _box(X0, Y0, X1, Y0 + 70) + r'{\p0}', 12)
    ev(c0, c1, 'HUD', r'{%s\an7\pos(%d,%d)\fs48\1c&HFFFFFF&\bord0\shad0}//// %s · %s' % (fx, X0 + 26, Y0 + 6, name, tag), 13)
    PX, PY, PW, PH = X0 + 60, Y0 + 150, X1 - X0 - 120, 200
    full, X, Y = _prof(0, DMAX, PX, PY, PW, PH, AMIN, AMAX)
    ev(c0, c1, 'Draw', r'{' + fx + r'\an7\pos(0,0)\1c' + INK_ + r'\1a&HB0&\p1}' + poly(full) + r'{\p0}', 12)
    done, _, _ = _prof(0, r0[3], PX, PY, PW, PH, AMIN, AMAX, dom=(0, DMAX))
    ev(c0, c1, 'Draw', r'{' + fx + r'\an7\pos(0,0)\1c' + INK_ + r'\1a&H10&\p1}' + poly(done) + r'{\p0}', 13)
    boss, _, _ = _prof(k0 * 1000, k1 * 1000, PX, PY, PW, PH, AMIN, AMAX, dom=(0, DMAX))
    ev(c0 + 0.7, c1, 'Draw', r'{\fad(300,350)\an7\pos(0,0)\1c' + SKY_ + r'\p1}' + poly(boss) + r'{\p0}', 13)
    xs = [r for r in REC if r[2] and r[3] is not None and k0 * 1000 <= r[3] <= k1 * 1000]; top = max(xs, key=lambda r: r[2])
    tx, ty = X(top[3]), Y(top[2])
    ev(c0 + 0.9, c1, 'HUD', r'{\fad(200,350)\an2\pos(%d,%d)\fs44\1c%s\3c%s\bord5\shad0\fscx130\fscy130\t(0,200,\fscx100\fscy100)}%s\N▼' % (tx, ty - 10, INK_, CREAM_, name), 15)
    x, y = X(r0[3]), Y(r0[2])
    ev(c0, c1, 'HUD', r'{%s\an2\pos(%d,%d)\fs32\1c%s\3c%s\bord4\shad0}เราอยู่ตรงนี้\N▼' % (fx, x, y + 2, INK_, CREAM_), 15)
    g_ = gain_between(xs[0][3], top[3])
    ev(c0 + 0.9, c1, 'HUD', r'{\fad(250,350)\an1\pos(%d,%d)\fs40\1c%s\bord0\shad0}%s: ขึ้น +%s M ใน %.0f KM · ยอด %s M' % (X0 + 30, Y1 - 18, INK_, name, f'{g_:,.0f}', k1 - k0, f'{top[2]:,.0f}'), 14)

def climb_card(s):
    """full-screen climb insert: zoomed profile of the climb, start/top labels, grade + time stats"""
    k0, k1, title = s['climb'][:3]
    xs = [r for r in REC if r[2] and r[3] is not None and k0 * 1000 <= r[3] <= k1 * 1000]
    top = max(xs, key=lambda r: r[2]); low = min((r for r in xs if r[3] <= top[3]), key=lambda r: r[2])
    seg_ = [r for r in xs if low[3] <= r[3] <= top[3]]
    mg = 0.0; j = 0
    for q in range(len(seg_)):
        while j < len(seg_) and seg_[j][3] - seg_[q][3] < 200: j += 1
        if j < len(seg_): mg = max(mg, (seg_[j][2] - seg_[q][2]) / (seg_[j][3] - seg_[q][3]) * 100)
    gain = top[2] - low[2]; dist = (top[3] - low[3]) / 1000; mins = (top[0] - low[0]) / 60
    a, b = seg_span(s); c0 = a + s.get('climb_at', 0.2); c1 = min(b, c0 + s.get('climb_dur', 8.0)); CARDS.append((c0, c1))
    fx = r'\fad(300,400)'
    ev(c0, c1, 'Draw', r'{' + fx + r'\an7\pos(0,0)\1c' + INK_ + r'\1a&H48&\p1}' + _box(0, 0, 1920, 1080) + r'{\p0}', 10)
    ev(c0, c1, 'Title', r'{%s\an7\pos(110,70)\fs110\1c&HFFFFFF&\3c%s\bord6}%s' % (fx, INK_, title), 13)
    sub = s['climb'][3] if len(s['climb']) > 3 else ''
    ev(c0 + 0.3, c1, 'Sub', r'{%s\an7\pos(118,215)\fs50\1c&HFFE8A6&}//// %s' % (fx, sub), 13)
    d0 = max(0, low[3] - 1500); d1 = min(DMAX, top[3] + 1500)
    PX, PY, PW, PH = 110, 360, 1700, 430
    lo_ = min(r[2] for r in REC if r[2] and r[3] is not None and d0 <= r[3] <= d1) - 40
    area, X, Y = _prof(d0, d1, PX, PY, PW, PH, lo_, top[2] + 40)
    ev(c0, c1, 'Draw', r'{' + fx + r'\an7\pos(0,0)\1c' + CREAM_ + r'\1a&H90&\p1}' + poly(area) + r'{\p0}', 11)
    climb, _, _ = _prof(low[3], top[3], PX, PY, PW, PH, lo_, top[2] + 40, dom=(d0, d1))
    xa, xb = X(low[3]), X(top[3])
    ev(c0 + 0.5, c1, 'Draw', r'{\fad(0,400)\an7\pos(0,0)\clip(%d,%d,%d,%d)\t(0,1800,\clip(%d,%d,%d,%d))\1c%s\bord3\3c&HFFFFFF&\p1}%s{\p0}' % (xa, PY - 40, xa + 1, PY + PH + 2, xa, PY - 40, xb + 4, PY + PH + 2, SKY_, poly(climb)), 12)
    def hmr(t): t %= 86400; return f'{int(t // 3600):02d}:{int(t % 3600 // 60):02d}'
    for r_, lab, t_ in ((low, 'เริ่มขึ้น', 0.3), (top, 'ยอด', 2.0)):
        x, y = X(r_[3]), Y(r_[2])
        ev(c0 + t_, c1, 'Draw', r'{\fad(200,400)\an7\pos(0,0)\1c&HFFFFFF&\bord4\3c' + INK_ + r'\p1}' + _box(x - 12, y - 12, x + 12, y + 12) + r'{\p0}', 14)
        an, xx = (r'\an3', x - 20) if x > 1300 else (r'\an1', x + 20)
        ev(c0 + t_, c1, 'HUD', r'{\fad(200,400)%s\pos(%d,%d)\fs40\1c&HFFFFFF&\3c%s\bord5\shad0}%s %s M\N{\fs30}KM %.1f' % (an, xx, y - 16, INK_, lab, f'{r_[2]:,.0f}', r_[3] / 1000), 14)
    stats = [(f'+{gain:,.0f} M', 'ขึ้น'), (f'{dist:.1f} KM', 'ระยะ'), (f'{gain / dist / 10:.0f}%', 'ชันเฉลี่ย'), (f'{mg:.0f}%', 'ชันสุด')]
    for q, (v, l) in enumerate(stats):
        x = 110 + q * 430
        ev(c0 + 2.2 + q * 0.18, c1, 'HUD', r'{\fad(200,400)\an7\pos(%d,850)\fs86\1c&HFFFFFF&\3c%s\bord5\shad0}%s\N{\fs36\1c&HFFE8A6&}%s' % (x, INK_, v, l), 14)

def pace_card(s):
    """full-screen per-km split bars: pace=(km0, km1, hl0, hl1, title, sub) - bars hl0..hl1 in the accent colour"""
    k0, k1, h0, h1, title, sub = s['pace']
    T_ = [r[3] for r in REC]
    def t_at(d): return REC[min(bisect.bisect_left(T_, d), len(REC) - 1)][0]
    sp = [((t_at((k + 1) * 1000) - t_at(k * 1000)) / 60, k) for k in range(int(k0), int(k1))]
    base = (t_at(int(k0) * 1000) - t_at(0)) / 60 / max(1, k0)
    a, b = seg_span(s); c0 = a + s.get('pace_at', 0.2); c1 = c0 + s.get('pace_dur', 9.0); CARDS.append((c0, c1))
    fx = r'\fad(300,400)'
    ev(c0, c1, 'Draw', r'{' + fx + r'\an7\pos(0,0)\1c' + INK_ + r'\1a&H40&\p1}' + _box(0, 0, 1920, 1080) + r'{\p0}', 10)
    ev(c0, c1, 'Title', r'{%s\an7\pos(110,60)\fs100\1c&HFFFFFF&\3c%s\bord6}%s' % (fx, INK_, title), 13)
    ev(c0 + 0.3, c1, 'Sub', r'{%s\an7\pos(118,195)\fs46\1c&HFFE8A6&}//// %s' % (fx, sub), 13)
    X0, Y0, W_, H_ = 140, 330, 1640, 500; CAP = 25.0
    bw = W_ / len(sp)
    yb = Y0 + H_
    yl = yb - base / CAP * H_      # early-race average pace line
    for q, (m, k) in enumerate(sp):
        x = X0 + q * bw; h = min(m, CAP) / CAP * H_
        hl = h0 <= k < h1
        stop = any(st['wkm'] >= k * 1000 and st['wkm'] < (k + 1) * 1000 for st in STN) and m > 2.5 * base
        col = SKY_ if hl else CREAM_
        d = 0.4 + q * 0.06
        ev(c0 + d, c1, 'Draw', r'{\fad(150,400)\an7\pos(0,0)\1c%s%s\p1}%s{\p0}' % (col, r'\1a&H70&' if stop else '', _box(x + 6, yb - h, x + bw - 6, yb)), 12)
        lab = ('พัก' if stop else f'{m:.0f}')
        ev(c0 + d, c1, 'HUD', r'{\fad(150,400)\an2\pos(%d,%d)\fs%d\1c&HFFFFFF&\3c%s\bord3\shad0}%s' % (x + bw / 2, yb - h - 6, 34 if hl else 28, INK_, lab), 13)
        ev(c0, c1, 'HUD', r'{%s\an8\pos(%d,%d)\fs26\1c&HFFE8A6&\bord0\shad0}%d' % (fx, x + bw / 2, yb + 6, k), 13)
    ev(c0 + 0.4, c1, 'Draw', r'{%s\an7\pos(0,0)\1c&HFFFFFF&\1a&H40&\p1}%s{\p0}' % (fx, _box(X0, yl - 2, X0 + W_, yl + 2)), 13)
    ev(c0 + 0.4, c1, 'HUD', r'{%s\an1\pos(%d,%d)\fs30\1c&HFFFFFF&\bord0\shad0}เฉลี่ย %d กิโลแรก %.0f นาที/กม.' % (fx, X0 + 8, yl - 6, k0, base), 13)
    hs = [m for m, k in sp if h0 <= k < h1 and m <= 2.5 * base]
    ev(c0 + 1.6, c1, 'HUD', r'{\fad(200,400)\an7\pos(%d,%d)\fs52\1c&HFFFFFF&\3c%s\bord5\shad0}KM %d–%d: เฉลี่ย %.0f นาที/กม.  ·  ช้าสุด %.0f นาที  {\fs34\1c&HFFE8A6&}(นาที/กม.)' % (X0, yb + 60, INK_, h0, h1, sum(hs) / len(hs), max(hs)), 13)

def build_ass():
    EV.clear(); EXTRA_SFX.clear(); BLING.clear(); SHUTTER.clear(); CARDS.clear()
    for S in SECTIONS:
        for s in S['segs']:
            if (s.get('st') or s.get('where')) and HAVE_GPS and STN: station_card(s)
            if s.get('climb') and HAVE_GPS: climb_card(s)
            if s.get('pace') and HAVE_GPS: pace_card(s)
            if s.get('boss') and HAVE_GPS: boss_card(s)
    # captions & callouts
    for S in SECTIONS:
        for s in S['segs']:
            a, b = seg_span(s)
            if s.get('cap'):
                c0 = tl_time(s, s['cap_at']) if 'cap_at' in s else a
                big = r'\fs110\frz4' if s.get('fx') == 'gauge' else ''
                if any(k0 - 0.3 <= c0 < k1 for k0, k1 in CARDS): big += r'\an2\pos(960,545)'     # sit above a station card
                ev(c0, min(b, c0 + 4.5), 'Cap', r'{\fad(120,200)' + big + r'\fscx80\fscy80\t(0,150,\fscx100\fscy100)}' + s['cap'], 5)
            if s.get('fx') == 'gauge':
                c0 = tl_time(s, s['cap_at'])
                # fuel gauge icon next to the caption: arc + needle swinging to F
                gx, gy = 1500, 905
                ev(c0, min(b, c0 + 4.5), 'Draw', r'{\fad(120,200)\an7\pos(0,0)\1c&HE8F1F4&\bord5\3c&HB45F1D&\p1}m %d %d b %d %d %d %d %d %d l %d %d{\p0}' % (gx-90, gy, gx-90, gy-120, gx+90, gy-120, gx+90, gy, gx-90, gy), 6)
                ev(c0, min(b, c0 + 4.5), 'HUD', r'{\fad(120,200)\an5\pos(%d,%d)\fs40\1c&H1D5FB4&\bord0\shad0}E{\fs40}               F' % (gx, gy - 20), 7)
                ev(c0, min(b, c0 + 4.5), 'Draw', (r'{\fad(120,200)\an7\org(%d,%d)\pos(0,0)\1c&HB45F1D&' + (r'\frz-60\t(0,900,\frz80)' if s.get('gauge_dir') == 'empty' else r'\frz80\t(0,700,\frz-60)') + r'\p1}m %d %d l %d %d l %d %d l %d %d{\p0}') % (gx, gy-10, gx-5, gy-10, gx-3, gy-100, gx+3, gy-100, gx+5, gy-10), 8)
                ev(c0 + 0.7, min(b, c0 + 4.5), 'HUD', r'{\an5\pos(%d,%d)\fs44\1c&HFFFFFF&\3c&HB45F1D&\bord5\frz12\fscx150\fscy150\t(0,180,\fscx100\fscy100)}%s' % (gx + 110, gy - 120, s.get('gauge_text', 'FULL!')), 8)
            if s.get('fx') == 'shutter':      # camera-shutter flash at the start of this segment (freeze-frame -> photo)
                SHUTTER.append(a)
                ev(max(0, a - 0.04), a + 0.18, 'Draw', r'{\an7\pos(0,0)\1c&HFFFFFF&\fad(0,140)\p1}m 0 0 l 1920 0 l 1920 1080 l 0 1080{\p0}', 9)
            if s.get('fx') == 'stamp':
                c0 = tl_time(s, s['fx_at'])
                EXTRA_SFX.append(c0)
                ev(c0, c0 + 0.12, 'Draw', r'{\an7\pos(0,0)\1c&HFFFFFF&\1a&H40&\p1}m 0 0 l 1920 0 l 1920 1080 l 0 1080{\p0}', 9)
                ev(c0, c0 + 3.2, 'Draw', r'{\fad(0,300)\an7\pos(0,0)\1c&HB45F1D&\1a&H30&\p1}m 0 380 l 1920 300 l 1920 700 l 0 780{\p0}', 8)
                ev(c0, c0 + 3.2, 'Title', (r'{\an5\pos(960,520)\fs%d\1c&HFFFFFF&' % s.get('stamp_fs', 230)) + r'\3c&HB45F1D&\bord10\frz-6\fscx320\fscy320\t(0,160,\fscx92\fscy92)\t(160,260,\fscx100\fscy100)\fad(0,300)}' + s['stamp'], 9)
                if s.get('stamp_sub'): ev(c0 + 0.35, c0 + 3.2, 'Sub', r'{\an5\pos(960,690)\fs62\1c&HE8F1F4&\frz-6\fad(150,300)}//// ' + s.get('stamp_sub', ''), 9)
            if s.get('bling'):
                t0b = tl_time(s, s['bling'])
                BLING.append((t0b, s))
                if s.get('bling_label'):
                    ev(t0b, t0b + s.get('bling_dur', 4.0), 'Call', r'{\fad(200,300)}//// ' + s['bling_label'], 5)
            if s.get('call'):
                k0 = tl_time(s, s['call_at']) if 'call_at' in s else a + 0.3
                ev(k0, min(b, k0 + 4.5), 'Call', r'{\fad(200,300)}//// ' + s['call'], 5)
            if s.get('banner'):        # lower-left text insert: banner=(title, sub)
                k0 = tl_time(s, s['banner_at']) if 'banner_at' in s else a + 0.3; k1 = k0 + s.get('banner_dur', 4.5)
                bt, bs = s['banner']
                ev(k0, k1, 'Draw', r'{\fad(200,300)\an7\pos(0,0)\1c&HB45F1D&\1a&H18&\p1}m 0 760 l 1180 760 l 1120 1000 l 0 1000{\p0}', 6)
                ev(k0 + 0.1, k1, 'Title', r'{\fad(200,300)\an1\pos(80,905)\fs120\fscx80\fscy80\t(0,160,\fscx100\fscy100)}' + bt, 7)
                ev(k0 + 0.35, k1, 'Sub', r'{\fad(200,300)\an1\pos(86,975)\fs56\1c&HFFE8A6&}//// ' + bs, 7)
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
    NOHUD = set(CFG.get('hud_skip_sections', ['hook', 'montage', 'intro']))
    for p in TL:
        if p['seg'].get('title') or p['seg'].get('card') or p['seg'].get('hud') is False or SECTIONS[p['sec']]['name'] in NOHUD: continue
        if garmin_at(real_at(p)) is None: continue
        if any(c0 - 0.2 <= p['t0'] and p['t0'] + p['dur'] <= c1 + 0.2 for c0, c1 in CARDS): continue
        t0, t1 = p['t0'], p['t0'] + p['dur']
        def frame(t0, t1):
            ev(t0, t1, 'Draw', r'{\an7\pos(0,0)\1c' + INK + r'\1a&H30&\p1}' + box(PX0 + 8, PY0 + 8, PX0 + PW0 + 8, PY0 + PH0 + 8) + r'{\p0}', 0)
            ev(t0, t1, 'Draw', r'{\an7\pos(0,0)\1c' + CREAM + r'\bord3\3c' + INK + r'\p1}' + box(PX0, PY0, PX0 + PW0, PY0 + PH0) + r'{\p0}', 1)
            ev(t0, t1, 'Draw', r'{\an7\pos(0,0)\1c' + INK + r'\p1}' + box(PX0, PY0, PX0 + PW0, PY0 + 44) + r'{\p0}', 2)
            pv, nx = leg_at(real_at(p))
            head = f"//// {pv['code']} → {nx['code']}" if pv and nx else '//// LIVE DATA'
            ev(t0, t1, 'HUD', r'{\an7\pos(%d,%d)\fs30\1c&HFFFFFF&\bord0\shad0}%s' % (PX0 + 18, PY0 + 2, head), 3)
            ev(t0, t1, 'Draw', r'{\an7\pos(0,0)\1c' + INK + r'\1a&H40&\p1}' + poly(pp + [(GX + GW, GY + GH), (GX, GY + GH)]) + r'{\p0}', 2)

        k = 0.0
        while k < p['dur'] - 0.01:
            real = real_at(p, k)
            idx = bisect.bisect_left(RT, real)
            r = garmin_at(real)
            if r and r[2]:
                a, b = t0 + k, t0 + min(p['dur'], k + 1.0)
                gr = grade_at(min(idx, len(REC) - 1))
                st = r'{\an7\pos(%d,%d)\fs54\1c' + INK + r'\bord0\shad0}%s{\fs28} %s'
                if any(c0 - 0.2 <= a < c1 for c0, c1 in CARDS): k += 1.0; continue      # a station/climb card is up: it carries the data
                frame(a, b)
                ev(a, b, 'HUD', r'{\an9\pos(%d,%d)\fs40\1c&HFFFFFF&\bord0\shad0}%s' % (PX0 + PW0 - 16, PY0 - 1, hhmm(real)), 3)
                pv, nx = leg_at(real)
                if nx:
                    togo = max(0.0, (nx['wkm'] - r[3]) / 1000)
                    ev(a, b, 'Draw', r'{\an7\pos(0,0)\1c' + INK + r'\p1}' + box(PX0, PY0 + PH0 + 10, PX0 + PW0, PY0 + PH0 + 58) + r'{\p0}', 1)
                    ev(a, b, 'HUD', r'{\an7\pos(%d,%d)\fs31\1c&HFFFFFF&\bord0\shad0}ถัดไป %s %s · อีก %.1f KM' % (PX0 + 16, PY0 + PH0 + 14, nx['code'], nx['name'], togo), 3)
                ev(a, b, 'HUD', st % (PX0 + 22, PY0 + 52, f'♥ {r[1] or "–"}', 'BPM'), 3)
                ev(a, b, 'HUD', st % (PX0 + 232, PY0 + 52, f'{gr:+.0f}%', 'ชัน'), 3)
                ev(a, b, 'HUD', st % (PX0 + 22, PY0 + 118, f'▲ {r[2]:,.0f}', 'M'), 3)
                ev(a, b, 'HUD', st % (PX0 + 232, PY0 + 118, f'{r[3]/1000 + PRESTART_KM:.1f}', 'KM'), 3)
                done = [q for q in pp if q[0] <= GX + r[3] / DMAX * GW]
                if len(done) > 1:
                    ev(a, b, 'Draw', r'{\an7\pos(0,0)\1c' + INK + r'\p1}' + poly(done + [(done[-1][0], GY + GH), (GX, GY + GH)]) + r'{\p0}', 3)
                dx = GX + r[3] / DMAX * GW; dy = GY + GH - (r[2] - AMIN) / (AMAX - AMIN) * GH
                ev(a, b, 'Draw', r'{\an7\pos(0,0)\1c' + SKYC + r'\bord1.5\3c' + INK + r'\p1}' + poly([(dx - 9, dy - 18), (dx + 9, dy - 18), (dx, dy - 3)]) + r'{\p0}', 4)   # sky-blue arrow pointing down at the position
            k += 1.0
    # ---- chapter cards: cream band + mini route map with position ----
    CH = {S['name']: S['chapter'] for S in SECTIONS if S.get('chapter')}
    rp = route_path(0, 0, 1) if HAVE_GPS else []
    n = 0
    for si, S in enumerate(SECTIONS):
        if S['name'] not in CH: continue
        n += 1
        p = next(x for x in TL if x['sec'] == si)
        a, b = p['t0'], p['t0'] + min(CFG.get('chapter_dur', 5.0), sum(x['dur'] for x in TL if x['sec'] == si))
        real = real_at(p)
        r = garmin_at(real) or REC[0]
        fx = r'\fad(250,300)'
        ev(a, b, 'Draw', r'{' + fx + r'\an7\pos(0,0)\1c' + CREAM + r'\bord3\3c' + INK + r'\p1}' + box(0, 812, 1100, 1010) + r'{\p0}', 6)
        ev(a, b, 'Draw', r'{' + fx + r'\an7\pos(0,0)\1c' + INK + r'\p1}' + box(0, 812, 300, 1010) + r'{\p0}', 7)
        ev(a, b, 'HUD', r'{%s\an7\pos(40,826)\fs40\1c&HFFFFFF&\bord0\shad0}CHAPTER\N{\fs110}%02d' % (fx, n), 8)
        ev(a, b, 'HUD', r'{%s\an7\pos(330,830)\fs92\1c%s\bord0\shad0}%s' % (fx, INK, CH[S['name']]), 8)
        ev(a, b, 'HUD', r'{%s\an7\pos(336,946)\fs40\1c%s\bord0\shad0}//// KM %.1f  ·  ▲ %s M  ·  %s' % (fx, INK, (r[3] or 0)/1000 + PRESTART_KM, f'{r[2]:,.0f}' if r[2] else '-', hhmm(real)), 8)
        # mini route map
        mx, my, ms = 880, 830, 170
        pts = [(mx + x * ms, my + y * ms) for x, y in rp]
        ev(a, b, 'Draw', r'{' + fx + r'\an7\pos(0,0)\bord2.5\3c' + INK + r'\1a&HFF&\3a&H90&\p1}' + poly(pts + pts[::-1]) + r'{\p0}', 7)
        g = [x for x in REC[::40] if x[4]]
        cut = sum(1 for x in g if x[0] <= real)
        if cut > 1:
            dp = pts[:cut]
            ev(a, b, 'Draw', r'{' + fx + r'\an7\pos(0,0)\bord2.5\3c' + INK + r'\1a&HFF&\p1}' + poly(dp + dp[::-1]) + r'{\p0}', 8)
            x, y = dp[-1]
            ev(a, b, 'Draw', r'{' + fx + r'\an7\pos(0,0)\1c&HFFFFFF&\bord2\3c' + INK + r'\p1}' + circ(x, y, 6) + r'{\p0}', 9)
    if END_CARD: ev(TOTAL - END_CARD, TOTAL, 'Draw', r'{\an7\pos(0,0)\1c&HB45F1D&\p1}m 0 0 l 1920 0 l 1920 1080 l 0 1080{\p0}', 4)
    if END_CARD: ev(TOTAL - END_CARD, TOTAL, 'End', r'{\fad(400,400)}ตัดต่อโดย Claude Code\N{\fs44\1c&HFFE8A6&}ถ่ายทำ · ตัดต่อ · เพลง · ข้อมูล Garmin', 5)
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
        if os.path.exists(path): return cue, 'cached'      # short tracks are crossfade-looped in finish()
        body = json.dumps({'prompt': PROMPTS[cue], 'music_length_ms': ms, 'force_instrumental': True}).encode()
        req = urllib.request.Request('https://api.elevenlabs.io/v1/music', body, {'xi-api-key': key, 'Content-Type': 'application/json'})
        data = urllib.request.urlopen(req, timeout=600).read()
        open(path, 'wb').write(data)
        return cue, f'{ms/1000:.0f}s'
    with ThreadPoolExecutor(2) as ex:
        for r in ex.map(one, need): print('music', r)
    for name, text, sec_ in (('whoosh', 'quick cinematic whoosh swoosh transition sound effect', 1.2),
                             ('shutter', 'single crisp DSLR camera shutter click, mechanical, close up, no reverb', 0.6)):
        wh = f'{ROOT}/music/sfx_{name}.mp3'
        if os.path.exists(wh): continue
        body = json.dumps({'text': text, 'duration_seconds': sec_}).encode()
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
    nin = 1
    for i, (cue, st, ln) in enumerate(groups):
        path = f'{ROOT}/music/{cue}.mp3'
        aud = audible(path)
        fo = 2.5 if i == len(groups) - 1 else 1.2
        if aud >= ln * 0.88:      # slightly short: slow it down a touch
            tempo = f',atempo={max(0.88, aud / ln):.4f}' if aud < ln else ''
            ins += ['-i', path]; srcl = f'[{nin}:a]'; nin += 1
        else:                     # much too short: chain copies of the track with 4 s crossfades
            reps = math.ceil((ln - 4) / (aud - 4)) + 1; tempo = ''
            for k in range(reps):
                ins += ['-i', path]
                fc.append(f'[{nin + k}:a]aresample=48000,aformat=channel_layouts=stereo,atrim=0:{aud:.3f}[lp{i}_{k}]')
            prev = f'[lp{i}_0]'
            for k in range(1, reps):
                fc.append(f'{prev}[lp{i}_{k}]acrossfade=d=4:c1=tri:c2=tri[lx{i}_{k}]'); prev = f'[lx{i}_{k}]'
            srcl = prev; nin += reps
        fc.append(f'{srcl}aresample=48000,aformat=channel_layouts=stereo{tempo},apad,atrim=0:{ln:.3f},afade=in:d=0.4,afade=out:st={max(0, ln-fo):.3f}:d={fo},adelay={int(st*1000)}:all=1[m{i}]')
    n = len(groups)
    # music sits well under talking: a fixed -12 dB dip over every speech stretch (ramped), plus a light sidechain
    talk = []
    for p in TL:
        if p['mode'] != 'sp' and not (p['mode'] == 'act' and p['seg'].get('vol', 1) > 0.5): continue
        if talk and p['t0'] - talk[-1][1] < 1.6: talk[-1][1] = p['t0'] + p['dur']
        else: talk.append([p['t0'], p['t0'] + p['dur']])
    dip = '+'.join(f'clip((t-{a - 0.3:.2f})/0.3,0,1)*clip(({b + 0.6:.2f}-t)/0.6,0,1)' for a, b in talk) or '0'
    MV = CFG.get('music_volume', 0.5); MT = CFG.get('music_under_talk', 0.13)
    fc.append(''.join(f'[m{i}]' for i in range(n)) + f"amix=inputs={n}:normalize=0,volume=eval=frame:volume='{MV}-{MV - MT}*({dip})'[mus]")
    fc.append('[0:a]aresample=48000:async=1:min_hard_comp=0.02:first_pts=0,asplit=2[dlg][key]')   # fill the tiny gaps between concatenated pieces (keeps sync, full length)
    fc.append('[mus][key]sidechaincompress=threshold=0.03:ratio=4:attack=20:release=400:makeup=1[duck]')
    # whooshes at section changes
    starts = sorted({p['t0'] for p in TL if p is TL[0] or p['sec'] != TL[p['n'] - 1]['sec']} - {0.0})
    starts = sorted(starts + [t + 0.35 for t in EXTRA_SFX])
    ins += ['-i', f'{ROOT}/music/sfx_whoosh.mp3']
    wi = nin
    fc.append(f'[{wi}:a]aresample=48000,aformat=channel_layouts=stereo,volume=0.6,asplit={len(starts)}' + ''.join(f'[w{i}]' for i in range(len(starts))))
    for i, s0 in enumerate(starts): fc.append(f'[w{i}]adelay={int(max(0, s0-0.35)*1000)}:all=1[wd{i}]')
    extra = ''
    if SHUTTER:
        ins += ['-i', f'{ROOT}/music/sfx_shutter.mp3']; si_ = wi + 1
        fc.append(f'[{si_}:a]aresample=48000,aformat=channel_layouts=stereo,volume=1.4,asplit={len(SHUTTER)}' + ''.join(f'[sh{i}]' for i in range(len(SHUTTER))))
        for i, s0 in enumerate(SHUTTER): fc.append(f'[sh{i}]adelay={int(max(0, s0 - 0.05) * 1000)}:all=1[shd{i}]')
        extra = ''.join(f'[shd{i}]' for i in range(len(SHUTTER)))
    fc.append('[dlg][duck]' + ''.join(f'[wd{i}]' for i in range(len(starts))) + extra + f'amix=inputs={2+len(starts)+len(SHUTTER)}:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[aout]')
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
    stickers = list(CFG.get('stickers', []))
    for S_ in SECTIONS:          # seg overlay=(sprite, width, x, y): picture laid over the clip while it plays (e.g. a route map)
        for sg in S_['segs']:
            if sg.get('overlay'):
                f_, w_, x_, y_ = sg['overlay']; a_, b_ = seg_span(sg)
                k0 = tl_time(sg, sg['overlay_at']) if 'overlay_at' in sg else a_
                stickers.append(dict(file=f_, w=w_, x=x_, y=y_, t0=round(k0, 2), t1=round(min(b_, k0 + sg.get('overlay_dur', 99)), 2), anim='slide', wobble=0))
    for si, st in enumerate(stickers):
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
