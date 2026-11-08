"""Image generation through a getpod/claude-gateway style provider (async jobs).
usage: GETPOD_KEY=... [GETPOD_URL=https://provider.getpod.ai] python image.py <out.png> "<prompt>" [ref_image_https_url] [size=1792x1024] [model=codex-image/gpt-image]
- POST /v1/images/generations -> {task_id}; poll GET /v1/images/jobs/<id> until status done|failed; images[] are data: URIs or URLs.
- Reference images must be public https URLs (local files/data URIs are rejected). Ask the user before uploading personal photos.
- List models: GET /v1/models?kind=image  (supports_image_ref tells which accept a reference).
- Inside claude-gateway you can instead call the built-in generate_image MCP tool."""
import sys, os, json, time, base64, urllib.request
out, prompt = sys.argv[1], sys.argv[2]
ref = sys.argv[3] if len(sys.argv) > 3 and sys.argv[3] else None
size = sys.argv[4] if len(sys.argv) > 4 else '1792x1024'
model = sys.argv[5] if len(sys.argv) > 5 else 'codex-image/gpt-image'
B = os.environ.get('GETPOD_URL', 'https://provider.getpod.ai'); K = os.environ['GETPOD_KEY']
H = {'Authorization': f'Bearer {K}', 'Content-Type': 'application/json'}
body = {'model': model, 'prompt': prompt, 'size': size, 'n': 1}
if ref: body['image'] = ref
job = json.loads(urllib.request.urlopen(urllib.request.Request(f'{B}/v1/images/generations', json.dumps(body).encode(), H), timeout=60).read())
print('job', job)
for _ in range(120):
    d = json.loads(urllib.request.urlopen(urllib.request.Request(f"{B}/v1/images/jobs/{job['task_id']}", headers=H), timeout=30).read())
    if d.get('status') in ('done', 'failed'): break
    time.sleep(5)
if d.get('status') != 'done': sys.exit(f'failed: {d.get("error")}')
im = d['images'][0]
data = base64.b64decode(im.split(',', 1)[1]) if im.startswith('data:') else urllib.request.urlopen(im).read()
open(out, 'wb').write(data); print('saved', out, 'cost', d.get('cost'))
