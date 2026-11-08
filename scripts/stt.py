"""Transcribe work/audio/*.mp3 with ElevenLabs Scribe (word timestamps), then write work/transcript.txt.
usage: XI_KEY=... python stt.py <project_root> [language_code=tha]
Max 2 concurrent requests on small ElevenLabs plans."""
import json, os, sys, glob, subprocess, urllib.request, uuid
from concurrent.futures import ThreadPoolExecutor
ROOT = sys.argv[1]; LANG = sys.argv[2] if len(sys.argv) > 2 else 'tha'
W = os.path.join(ROOT, 'work'); KEY = os.environ.get('XI_KEY')

def scribe(mp3):
    out = os.path.join(W, 'stt', os.path.basename(mp3)[:-4] + '.json')
    if os.path.exists(out) and 'words' in open(out).read(): return out
    if not KEY: sys.exit('XI_KEY not set')
    b = uuid.uuid4().hex; parts = []
    for k, v in (('model_id', 'scribe_v1'), ('language_code', LANG), ('tag_audio_events', 'true'), ('timestamps_granularity', 'word')):
        parts.append(f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    parts.append(f'--{b}\r\nContent-Disposition: form-data; name="file"; filename="a.mp3"\r\nContent-Type: audio/mpeg\r\n\r\n'.encode() + open(mp3, 'rb').read() + b'\r\n')
    body = b''.join(parts) + f'--{b}--\r\n'.encode()
    req = urllib.request.Request('https://api.elevenlabs.io/v1/speech-to-text', body, {'xi-api-key': KEY, 'Content-Type': f'multipart/form-data; boundary={b}'})
    open(out, 'wb').write(urllib.request.urlopen(req, timeout=600).read()); return out

files = sorted(glob.glob(os.path.join(W, 'audio', '*.mp3')))
with ThreadPoolExecutor(2) as ex: list(ex.map(scribe, files))

raw = {os.path.basename(p).split('_')[2] if p.count('_') >= 2 else os.path.basename(p)[:-4]: p for p in glob.glob(os.path.join(ROOT, 'raw', '*.*'))}
with open(os.path.join(W, 'transcript.txt'), 'w') as out:
    for j in sorted(glob.glob(os.path.join(W, 'stt', '*.json'))):
        n = os.path.basename(j)[:-5]; d = json.load(open(j))
        rp = raw.get(n, ''); fn = os.path.basename(rp)
        hhmm = f'{fn[12:14]}:{fn[14:16]}' if fn.startswith('DJI_') else '--:--'
        dur = float(subprocess.check_output(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', rp]).decode()) if rp else 0
        out.write(f'\n## {hhmm} clip{n} ({dur:.0f}s)\n'); seg = None
        for w in d.get('words', []):
            if w['type'] == 'spacing': continue
            t = f"[{w['text'].strip('()[]')}]" if w['type'] == 'audio_event' else w['text']
            if seg and w['start'] - seg[1] < 0.8: seg[1] = w['end']; seg[2] += t
            else:
                if seg: out.write(f'{seg[0]:6.1f}-{seg[1]:6.1f} {seg[2]}\n')
                seg = [w['start'], w['end'], t]
        if seg: out.write(f'{seg[0]:6.1f}-{seg[1]:6.1f} {seg[2]}\n')
print('transcript:', os.path.join(W, 'transcript.txt'))
