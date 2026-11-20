"""Fit a homography from each close-up board photo to the overview photo (SIFT + RANSAC).
Writes photos/homographies.json: {name: 3x3 matrix mapping close-up px -> overview px}."""
import json, cv2, numpy as np
ov = cv2.imread("photos/overview.jpg", cv2.IMREAD_GRAYSCALE)
sift = cv2.SIFT_create(8000)
kov, dov = sift.detectAndCompute(ov, None)
out = {}
for name in ["nw", "ne", "sw", "se"]:
    im = cv2.imread(f"photos/{name}.jpg", cv2.IMREAD_GRAYSCALE)
    k, d = sift.detectAndCompute(im, None)
    m = cv2.BFMatcher().knnMatch(d, dov, k=2)
    good = [a for a, b in m if a.distance < 0.7 * b.distance]
    src = np.float32([k[g.queryIdx].pt for g in good])
    dst = np.float32([kov[g.trainIdx].pt for g in good])
    H, mask = cv2.findHomography(src, dst, cv2.RANSAC, 4.0)
    inl = int(mask.sum())
    err = np.linalg.norm(cv2.perspectiveTransform(src[mask.ravel() == 1][None], H)[0] - dst[mask.ravel() == 1], axis=1)
    print(name, "matches", len(good), "inliers", inl, "median err px", round(float(np.median(err)), 2))
    out[name] = H.tolist()
json.dump(out, open("photos/homographies.json", "w"), indent=1)
