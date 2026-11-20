"""Snap each room node in board.txt onto the center of its colored room tile in photos/mosaic.jpg.

Finds every room-sized blob of each level's color across the whole board, then assigns rooms to blobs
one-to-one (Hungarian, by distance) so two rooms can't land on the same tile.
Prints old -> new; --write rewrites the room lines; --debug writes the blob masks to the scratch dir."""
import re, sys, cv2, numpy as np
from pathlib import Path
from scipy.optimize import linear_sum_assignment

ROOT = Path(__file__).resolve().parent.parent
# per level: (hue lo, hue hi, min S, min V) in OpenCV HSV, tuned on sampled room floors
COLOR = {1: [(18, 35, 70, 110)], 2: [(8, 25, 70, 110)], 3: [(0, 12, 90, 110), (170, 179, 90, 110)],
         4: [(150, 179, 50, 110)], 5: [(98, 125, 25, 95)], 6: [(72, 100, 35, 60)]}
img = cv2.imread(str(ROOT / "photos/mosaic.jpg"))
hsv = cv2.cvtColor(cv2.GaussianBlur(img, (9, 9), 0), cv2.COLOR_BGR2HSV)
H, S, V = hsv[..., 0], hsv[..., 1], hsv[..., 2]


def blobs(lv):
    m = np.zeros(H.shape, np.uint8)
    for lo, hi, smin, vmin in COLOR[lv]:
        m |= ((H >= lo) & (H <= hi) & (S >= smin) & (V >= vmin)).astype(np.uint8)
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((11, 11), np.uint8))
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))
    n, lab, st, cen = cv2.connectedComponentsWithStats(m)
    out = []
    for i in range(1, n):
        a = st[i, cv2.CC_STAT_AREA]
        w, h = st[i, cv2.CC_STAT_WIDTH], st[i, cv2.CC_STAT_HEIGHT]
        if 7000 <= a <= 45000 and 0.5 < w / h < 2.0:
            out.append((cen[i][0], cen[i][1], a))
    return out


text = (ROOT / "board.txt").read_text().split("\n")
rooms = {}
for k, ln in enumerate(text):
    m = re.match(r"room (\S+) (\d) (\d+),(\d+)(.*)", ln)
    if m:
        rooms[m.group(1)] = dict(line=k, lv=int(m.group(2)), x=int(m.group(3)), y=int(m.group(4)), rest=m.group(5))

for lv in range(1, 7):
    ids = [r for r, v in rooms.items() if v["lv"] == lv]
    bl = blobs(lv)
    print(f"L{lv}: {len(ids)} rooms, {len(bl)} candidate tiles")
    if not bl:
        continue
    cost = np.array([[np.hypot(bx - rooms[r]["x"], by - rooms[r]["y"]) for bx, by, _ in bl] for r in ids])
    ri, ci = linear_sum_assignment(cost)
    for a, b in zip(ri, ci):
        r = rooms[ids[a]]
        bx, by, area = bl[b]
        d = cost[a, b]
        flag = "  <-- CHECK" if d > 120 else ""
        print(f"  {ids[a]}: {r['x']},{r['y']} -> {bx:.0f},{by:.0f}  moved {d:.0f}  area {area}{flag}")
        if d <= 160:
            text[r["line"]] = f"room {ids[a]} {lv} {bx:.0f},{by:.0f}{r['rest']}"
    for a in set(range(len(ids))) - set(ri):
        print(f"  {ids[a]}: no tile assigned")

if "--write" in sys.argv:
    (ROOT / "board.txt").write_text("\n".join(text))
