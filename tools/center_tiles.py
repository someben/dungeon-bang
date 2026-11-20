"""Snap each hallway node in board.txt onto the center of the flagstone tile it sits on (photos/mosaic.jpg).

Tile = connected region of floor pixels bounded by grout/edge lines, found by flood-filling an edge map from
the node (or from the nearest non-edge pixel). Region must be tile-sized, else the node is left alone.
Prints moves; --write rewrites coordinates (chain/hall lines) in board.txt."""
import re, sys, cv2, numpy as np
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from board import parse

ROOT = Path(__file__).resolve().parent.parent
img = cv2.imread(str(ROOT / "photos/mosaic.jpg"))
gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
blur = cv2.GaussianBlur(gray, (5, 5), 0)
edges = cv2.Canny(blur, 30, 80)
edges = cv2.dilate(edges, np.ones((3, 3), np.uint8))
dark = (blur < 95).astype(np.uint8)  # walls/rock
barrier = ((edges > 0) | (dark > 0)).astype(np.uint8)
H, W = gray.shape
MIN_A, MAX_A, MAX_MOVE = 2500, 16000, 60


def tile_center(x, y):
    best = None
    for dx, dy in [(0, 0)] + [(dx, dy) for r in (6, 12, 18) for dx in (-r, 0, r) for dy in (-r, 0, r) if (dx, dy) != (0, 0)]:
        sx, sy = int(x + dx), int(y + dy)
        if not (0 <= sx < W and 0 <= sy < H) or barrier[sy, sx]:
            continue
        x0, y0 = max(0, sx - 130), max(0, sy - 130)
        sub = barrier[y0:sy + 130, x0:sx + 130].copy()
        mask = np.zeros((sub.shape[0] + 2, sub.shape[1] + 2), np.uint8)
        cv2.floodFill(sub, mask, (sx - x0, sy - y0), 2, flags=4)
        reg = sub == 2
        a = int(reg.sum())
        if not (MIN_A <= a <= MAX_A):
            continue
        ys, xs = np.nonzero(reg)
        # touching the window border means it leaked out of a tile
        if xs.min() == 0 or ys.min() == 0 or xs.max() == sub.shape[1] - 1 or ys.max() == sub.shape[0] - 1:
            continue
        cx, cy = xs.mean() + x0, ys.mean() + y0
        d = np.hypot(cx - x, cy - y)
        if d <= MAX_MOVE and (best is None or a > best[2]):
            best = (cx, cy, a)
    return best


nodes, _ = parse(ROOT / "board.txt")
new = {}
for n, v in nodes.items():
    if v["kind"] != "hall":
        continue
    x, y = v["xy"]
    r = tile_center(x, y)
    if r:
        new[n] = (round(r[0]), round(r[1]))
        print(f"{n}: {x:.0f},{y:.0f} -> {new[n][0]},{new[n][1]}  area {r[2]}")
    else:
        print(f"{n}: {x:.0f},{y:.0f}  KEPT (no clean tile found)")
print(f"moved {len(new)} of {sum(1 for v in nodes.values() if v['kind'] == 'hall')}")

if "--write" in sys.argv:
    lines = (ROOT / "board.txt").read_text().split("\n")
    for i, ln in enumerate(lines):
        code, _, com = ln.partition("#")
        t = code.split()
        if not t:
            continue
        if t[0] == "hall" and t[1] in new:
            t[2] = "%d,%d" % new[t[1]]
        elif t[0] == "chain":
            for k in range(2, len(t)):
                nid = f"{t[1]}{k - 1}"
                if nid in new:
                    t[k] = "%d,%d" % new[nid]
        else:
            continue
        lines[i] = " ".join(t) + ("      #" + com if com else "")
    (ROOT / "board.txt").write_text("\n".join(lines))
