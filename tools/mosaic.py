"""Warp the four close-ups into the overview frame at 2x scale -> photos/mosaic.jpg (sharp full-board image).
Board coordinates used everywhere else are mosaic pixels (= overview px * 2)."""
import json, cv2, numpy as np
S = 2.0
Hs = json.load(open("photos/homographies.json"))
ov = cv2.imread("photos/overview.jpg")
h, w = ov.shape[:2]
W, Hh = int(w * S), int(h * S)
canvas = cv2.resize(ov, (W, Hh), interpolation=cv2.INTER_CUBIC).astype(np.float32)
best = np.full((Hh, W), np.inf, np.float32)
yy, xx = np.mgrid[0:Hh, 0:W].astype(np.float32)
scale = np.diag([S, S, 1.0])
for name, H in Hs.items():
    im = cv2.imread(f"photos/{name}.jpg")
    M = scale @ np.array(H)
    warped = cv2.warpPerspective(im, M, (W, Hh), flags=cv2.INTER_CUBIC)
    valid = cv2.warpPerspective(np.ones(im.shape[:2], np.uint8), M, (W, Hh), flags=cv2.INTER_NEAREST) > 0
    valid = cv2.erode(valid.astype(np.uint8), np.ones((15, 15), np.uint8)) > 0
    # distance of each canvas pixel from the close-up's image center (in its own frame) -> prefer the most central view
    Minv = np.linalg.inv(M)
    den = Minv[2, 0] * xx + Minv[2, 1] * yy + Minv[2, 2]
    sx = (Minv[0, 0] * xx + Minv[0, 1] * yy + Minv[0, 2]) / den
    sy = (Minv[1, 0] * xx + Minv[1, 1] * yy + Minv[1, 2]) / den
    d = ((sx - im.shape[1] / 2) / im.shape[1]) ** 2 + ((sy - im.shape[0] / 2) / im.shape[0]) ** 2
    take = valid & (d < best)
    canvas[take] = warped[take]
    best[take] = d[take]
cv2.imwrite("photos/mosaic.jpg", canvas.astype(np.uint8), [cv2.IMWRITE_JPEG_QUALITY, 92])
print(W, Hh)
