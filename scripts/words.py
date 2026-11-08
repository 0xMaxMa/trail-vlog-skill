"""Print word-level timestamps for a clip window, to pick exact cut points.
usage: python words.py <project_root> <clip_no e.g. 0014> <from_s> <to_s>"""
import json, sys, glob, os
root, clip, a, b = sys.argv[1], sys.argv[2], float(sys.argv[3]), float(sys.argv[4])
d = json.load(open((glob.glob(os.path.join(root, 'work', 'stt', f'{clip}.json')) or glob.glob(os.path.join(root, 'work', 'stt', f'*_{clip}_*.json')))[0]))
print(clip, ' '.join(f"{w['start']:.1f}{w['text']}" for w in d['words'] if w['type'] != 'spacing' and a <= w['start'] <= b))
