"""Crop a region of a photo, upscale it, and overlay a labeled coordinate grid (in source-pixel units)."""
import sys
from PIL import Image, ImageDraw, ImageFont
src, x0, y0, w, h, scale, out = sys.argv[1], *map(int, sys.argv[2:6]), float(sys.argv[6]), sys.argv[7]
step = int(sys.argv[8]) if len(sys.argv) > 8 else 25
im = Image.open(src).convert("RGB").crop((x0, y0, x0 + w, y0 + h))
im = im.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
d = ImageDraw.Draw(im, "RGBA")
font = ImageFont.load_default(size=14)
for gx in range((x0 // step + 1) * step, x0 + w, step):
    X = (gx - x0) * scale
    major = gx % (step * 2) == 0
    d.line([(X, 0), (X, im.height)], fill=(255, 255, 0, 150) if major else (0, 255, 255, 90), width=1)
    if major:
        d.text((X + 2, 2), str(gx), fill=(255, 255, 0, 255), font=font, stroke_width=2, stroke_fill=(0, 0, 0))
for gy in range((y0 // step + 1) * step, y0 + h, step):
    Y = (gy - y0) * scale
    major = gy % (step * 2) == 0
    d.line([(0, Y), (im.width, Y)], fill=(255, 255, 0, 150) if major else (0, 255, 255, 90), width=1)
    if major:
        d.text((2, Y + 2), str(gy), fill=(255, 255, 0, 255), font=font, stroke_width=2, stroke_fill=(0, 0, 0))
im.save(out, quality=90)
