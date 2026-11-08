"""Turn an AI-generated sticker on flat #00FF00 green into a cropped transparent PNG.
usage: python sprite_key.py <in.png> <out.png>
Tip: prompt the image model with 'isolated on a pure flat chroma-key green background (#00FF00), no shadow, no text'."""
import sys
import numpy as np
from PIL import Image
a = np.array(Image.open(sys.argv[1]).convert('RGBA')).astype(float)
r, g, b = a[..., 0], a[..., 1], a[..., 2]
a[..., 3] = np.clip(1 - ((g - np.maximum(r, b)) - 40) / 80, 0, 1) * 255
a[..., 1] = np.minimum(g, np.maximum(r, b) + 10)
im = Image.fromarray(a.astype('uint8'), 'RGBA'); im = im.crop(im.getbbox()); im.save(sys.argv[2]); print(sys.argv[2], im.size)
