"""Write output/<name>_th.srt for YouTube from the Scribe transcript, mapped onto the edited timeline.
usage: python srt.py <project_root>
Cues split at speech pauses (never mid-word); only 1x speech pieces get subs. Word fixes come from project.json "srt_fixes": [[wrong, right], ...]."""
import sys, os, json, glob, re
ROOT = os.path.abspath(sys.argv[1]); os.environ['TRAIL_ROOT'] = ROOT; os.chdir(os.path.join(ROOT, 'work'))
sys.argv = ['build.py', 'proxy', '--plan']
exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'build.py')).read().split("if __name__ == '__main__':")[0])
FIX = CFG.get('srt_fixes', [])
def fmt(x):
    ms = int(round(x * 1000)); h, ms = divmod(ms, 3600000); m, ms = divmod(ms, 60000); s, ms = divmod(ms, 1000)
    return f'{h:02d}:{m:02d}:{s:02d},{ms:03d}'
cues = []
for p in TL:
    if p['speed'] != 1.0 or p['mode'] == 'br': continue
    d = json.load(open((glob.glob(f"stt/{p['clip']}.json") or glob.glob(f"stt/*_{p['clip']}_*.json"))[0]))
    ws = [w for w in d['words'] if w['type'] == 'word' and w['start'] >= p['a'] - 0.05 and w['end'] <= p['b'] + 0.05]
    groups = []
    for w in ws:
        if groups and w['start'] - groups[-1][-1]['end'] < 0.35: groups[-1].append(w)
        else: groups.append([w])
    def split(g):
        if g[-1]['end'] - g[0]['start'] <= 5.0 or len(g) < 4: return [g]
        k = max(range(2, len(g) - 1), key=lambda i: (g[i]['start'] - g[i-1]['end'], -abs(i - len(g) / 2)))
        return split(g[:k]) + split(g[k:])
    for g in groups:
        for h in split(g):
            cues.append([p['t0'] + h[0]['start'] - p['a'], p['t0'] + h[-1]['end'] - p['a'], ''.join(w['text'] for w in h)])
cues.sort(key=lambda c: c[0])
for i in range(len(cues) - 1): cues[i][1] = min(max(cues[i][1], cues[i][0] + 0.8), cues[i+1][0] - 0.02)
out = []
for a, b, t in cues:
    for x, y in FIX: t = t.replace(x, y)
    t = re.sub(r'([A-Za-z])([฀-๿])', r'\1 \2', t); t = re.sub(r'([฀-๿])([A-Za-z])', r'\1 \2', t).strip()
    if t: out.append(f'{len(out)+1}\n{fmt(a)} --> {fmt(b)}\n{t}\n')
path = os.path.join(ROOT, 'output', f"{CFG.get('output_name', 'trail_vlog')}_th.srt")
open(path, 'w').write('\n'.join(out)); print(len(out), 'cues ->', path)
