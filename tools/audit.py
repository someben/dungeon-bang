"""Audit render: contrast-enhanced board with the graph drawn lightly (rings + thin lines) so tile lines stay visible.
audit.py X0 Y0 W H SCALE OUT"""
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
sys.path.insert(0, str(Path(__file__).resolve().parent))
from board import parse, ROOT
x0, y0, w, h = map(int, sys.argv[1:5]); sc = float(sys.argv[5]); out = sys.argv[6]
nodes, edges = parse()
im = Image.open(ROOT / "photos/mosaic_enh.jpg").convert("RGB").crop((x0, y0, x0 + w, y0 + h)).resize((int(w * sc), int(h * sc)), Image.LANCZOS)
d = ImageDraw.Draw(im, "RGBA"); f = ImageFont.load_default(size=12)
P = lambda n: ((nodes[n]["xy"][0] - x0) * sc, (nodes[n]["xy"][1] - y0) * sc)
for g in range((x0 // 100 + 1) * 100, x0 + w, 100):
    X = (g - x0) * sc; d.line([(X, 0), (X, 14)], fill=(0, 255, 255, 255)); d.text((X + 2, 0), str(g), fill=(0, 255, 255, 255), font=f, stroke_width=2, stroke_fill=(0, 0, 0))
for g in range((y0 // 100 + 1) * 100, y0 + h, 100):
    Y = (g - y0) * sc; d.line([(0, Y), (14, Y)], fill=(0, 255, 255, 255)); d.text((0, Y + 2), str(g), fill=(0, 255, 255, 255), font=f, stroke_width=2, stroke_fill=(0, 0, 0))
col = {"open": (255, 255, 0, 200), "door": (0, 255, 0, 230), "secret": (255, 0, 0, 230)}
for a, b, k in edges:
    d.line([P(a), P(b)], fill=col[k], width=1 if k == "open" else 2)
for n, v in nodes.items():
    x, y = P(n)
    if not (-20 < x < im.width + 20 and -20 < y < im.height + 20): continue
    r = 5 if v["kind"] == "hall" else 9
    d.ellipse([x - r, y - r, x + r, y + r], outline=(255, 0, 255, 255) if v["kind"] == "hall" else (0, 0, 0, 255), width=2)
    d.text((x + 6, y - 14), n, fill=(255, 255, 255, 255), font=f, stroke_width=2, stroke_fill=(0, 0, 0))
im.save(out, quality=90)
