"""Parse board.txt (the hand-traced board graph) and render overlays for checking.

DSL, one statement per line (coordinates are mosaic pixels, see tools/mosaic.py):
  chain P x,y x,y ...         hallway spaces P1..Pn, each adjacent to the next
  hall ID x,y                 one hallway space
  room ID LEVEL x,y           a room (1 monster + treasure)
  chamber ID LEVEL x,y Name   a chamber (3 monsters, no treasure); LEVEL 0 = Great Hall
  link A B [C ...]            A-B adjacent (and B-C, ...): open passage, no door
  door A B                    regular door between A and B (doors are not spaces)
  secret A B                  secret door between A and B
  merge A INTO B              A is really part of B (a chamber): drop A, reattach its edges to B
Usage:
  board.py check
  board.py render X0 Y0 W H SCALE OUT [GRID]   overlay on photos/mosaic.jpg
"""
import re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEVEL_RGB = {0: (255, 255, 255), 1: (250, 230, 90), 2: (250, 160, 40), 3: (230, 60, 40),
             4: (230, 80, 200), 5: (70, 110, 240), 6: (20, 200, 190)}


def xy(s):
    x, y = s.split(",")
    return float(x), float(y)


def parse(path=ROOT / "board.txt"):
    merges = []
    nodes, edges = {}, []  # nodes: id -> dict(kind, level, x, y, name); edges: (a, b, kind)
    for ln, raw in enumerate(Path(path).read_text().splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        t = line.split()
        op = t[0]
        def add(i, **kw):
            if i in nodes:
                raise SystemExit(f"line {ln}: duplicate node {i}")
            nodes[i] = kw
        if op == "chain":
            p = t[1]
            prev = None
            for k, c in enumerate(t[2:], 1):
                i = f"{p}{k}"
                add(i, kind="hall", level=None, xy=xy(c))
                if prev:
                    edges.append((prev, i, "open", ln))
                prev = i
        elif op == "hall":
            add(t[1], kind="hall", level=None, xy=xy(t[2]))
        elif op == "room":
            add(t[1], kind="room", level=int(t[2]), xy=xy(t[3]))
        elif op == "chamber":
            add(t[1], kind="chamber", level=int(t[2]), xy=xy(t[3]), name=" ".join(t[4:]))
        elif op == "link":
            for a, b in zip(t[1:], t[2:]):
                edges.append((a, b, "open", ln))
        elif op in ("door", "secret"):
            edges.append((t[1], t[2], op, ln))
        elif op == "merge":
            merges.append((t[1], t[3], ln))
        else:
            raise SystemExit(f"line {ln}: unknown op {op}")
    for a, b, ln in merges:
        if a not in nodes or b not in nodes:
            raise SystemExit(f"line {ln}: unknown node in merge {a} {b}")
        del nodes[a]
        edges = [(b if x == a else x, b if y == a else y, k, l) for x, y, k, l in edges]
    out, seen = [], set()
    for a, b, k, ln in edges:
        for n in (a, b):
            if n not in nodes:
                raise SystemExit(f"line {ln}: unknown node {n}")
        key = frozenset((a, b))
        if a == b or key in seen:
            continue
        seen.add(key)
        out.append((a, b, k))
    return nodes, out


def check():
    nodes, edges = parse()
    deg = {n: 0 for n in nodes}
    seen = set()
    for a, b, k in edges:
        deg[a] += 1; deg[b] += 1
        key = frozenset((a, b))
        if key in seen:
            print("duplicate edge", a, b)
        seen.add(key)
        for n, m in ((a, b), (b, a)):
            if nodes[n]["kind"] in ("room", "chamber") and nodes[m]["kind"] == "room":
                pass
        if nodes[a]["kind"] == "room" or nodes[b]["kind"] == "room":
            if k == "open":
                print("room joined without a door:", a, b)
    for n, d in deg.items():
        if d == 0:
            print("isolated:", n)
    # connectivity from the Great Hall
    adj = {n: [] for n in nodes}
    for a, b, k in edges:
        adj[a].append(b); adj[b].append(a)
    start = next((n for n, v in nodes.items() if v["kind"] == "chamber" and v["level"] == 0), None)
    if start:
        seen, st = {start}, [start]
        while st:
            for m in adj[st.pop()]:
                if m not in seen:
                    seen.add(m); st.append(m)
        unreached = [n for n in nodes if n not in seen]
        if unreached:
            print("not reachable from Great Hall:", " ".join(sorted(unreached)))
    kinds = {}
    for v in nodes.values():
        key = v["kind"] if v["kind"] == "hall" else f'{v["kind"]} L{v["level"]}'
        kinds[key] = kinds.get(key, 0) + 1
    print(" ".join(f"{k}={v}" for k, v in sorted(kinds.items())), f"edges={len(edges)}")


def render(x0, y0, w, h, scale, out, grid=0):
    from PIL import Image, ImageDraw, ImageFont
    nodes, edges = parse()
    im = Image.open(ROOT / "photos/mosaic.jpg").convert("RGB").crop((x0, y0, x0 + w, y0 + h))
    im = im.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    d = ImageDraw.Draw(im, "RGBA")
    font = ImageFont.load_default(size=13)
    P = lambda n: ((nodes[n]["xy"][0] - x0) * scale, (nodes[n]["xy"][1] - y0) * scale)
    if grid:
        for gx in range((x0 // grid + 1) * grid, x0 + w, grid):
            X = (gx - x0) * scale
            d.line([(X, 0), (X, im.height)], fill=(0, 255, 255, 70), width=1)
            if gx % (grid * 2) == 0:
                d.text((X + 2, 2), str(gx), fill=(0, 255, 255, 255), font=font, stroke_width=2, stroke_fill=(0, 0, 0))
        for gy in range((y0 // grid + 1) * grid, y0 + h, grid):
            Y = (gy - y0) * scale
            d.line([(0, Y), (im.width, Y)], fill=(0, 255, 255, 70), width=1)
            if gy % (grid * 2) == 0:
                d.text((2, Y + 2), str(gy), fill=(0, 255, 255, 255), font=font, stroke_width=2, stroke_fill=(0, 0, 0))
    col = {"open": (255, 255, 255, 220), "door": (40, 255, 40, 255), "secret": (255, 40, 40, 255)}
    for a, b, k in edges:
        d.line([P(a), P(b)], fill=col[k], width=5 if k != "open" else 3)
    for n, v in nodes.items():
        x, y = P(n)
        if v["kind"] == "hall":
            d.ellipse([x - 7, y - 7, x + 7, y + 7], fill=(0, 0, 0, 230), outline=(255, 255, 255, 255), width=2)
        else:
            r = 14 if v["kind"] == "room" else 20
            d.rectangle([x - r, y - r, x + r, y + r], fill=LEVEL_RGB[v["level"]] + (255,), outline=(0, 0, 0, 255), width=3)
        d.text((x + 9, y - 16), n, fill=(255, 255, 0, 255), font=font, stroke_width=2, stroke_fill=(0, 0, 0))
    im.save(out, quality=90)


if __name__ == "__main__":
    if sys.argv[1] == "check":
        check()
    elif sys.argv[1] == "render":
        render(*map(int, sys.argv[2:6]), float(sys.argv[6]), sys.argv[7], int(sys.argv[8]) if len(sys.argv) > 8 else 0)
