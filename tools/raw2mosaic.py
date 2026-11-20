"""Map raw close-up photo pixel coords to mosaic coords: raw2mosaic.py PHOTO x,y [x,y ...]"""
import json, sys
import numpy as np
H = np.diag([2.0, 2.0, 1.0]) @ np.array(json.load(open("photos/homographies.json"))[sys.argv[1]])
for a in sys.argv[2:]:
    x, y = map(float, a.split(","))
    v = H @ [x, y, 1]
    print(f"{a} -> {v[0] / v[2]:.0f},{v[1] / v[2]:.0f}")
