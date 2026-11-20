"""Apply edits to the flat board.txt. Commands on stdin, one per line:
  mv ID x,y | add ID x,y | del ID | ren OLD NEW | link A B | door A B | secret A B | unlink A B | fold A B (A is part of B)"""
import sys
from pathlib import Path
p = Path(__file__).resolve().parent.parent / "board.txt"
L = p.read_text().split("\n")
def find(pred): return [i for i, l in enumerate(L) if pred(l.split())]
for raw in sys.stdin:
    c = raw.split("#")[0].split()
    if not c: continue
    op = c[0]
    if op == "mv":
        i = find(lambda t: len(t) > 1 and t[0] in ("hall", "room", "chamber") and t[1] == c[1]); assert len(i) == 1, raw
        t = L[i[0]].split(); t[2 if t[0] == "hall" else 3] = c[2]; L[i[0]] = " ".join(t)
    elif op == "add":
        assert not find(lambda t: len(t) > 1 and t[0] in ("hall", "room", "chamber") and t[1] == c[1]), raw
        j = max(find(lambda t: t and t[0] == "hall")); L.insert(j + 1, f"hall {c[1]} {c[2]}")
    elif op in ("link", "door", "secret"):
        for n in c[1:3]: assert find(lambda t: len(t) > 1 and t[0] in ("hall", "room", "chamber") and t[1] == n), raw
        assert not find(lambda t: len(t) == 3 and t[0] in ("link", "door", "secret") and {t[1], t[2]} == {c[1], c[2]}), "dup " + raw
        L.append(f"{op} {c[1]} {c[2]}")
    elif op == "unlink":
        i = find(lambda t: len(t) == 3 and t[0] in ("link", "door", "secret") and {t[1], t[2]} == {c[1], c[2]}); assert len(i) == 1, raw
        del L[i[0]]
    elif op == "del":
        i = find(lambda t: len(t) > 1 and t[0] == "hall" and t[1] == c[1]); assert len(i) == 1, raw
        del L[i[0]]
        L = [l for l in L if not (len(l.split()) == 3 and l.split()[0] in ("link", "door", "secret") and c[1] in l.split()[1:])]
    elif op == "ren":
        assert not find(lambda t: len(t) > 1 and t[0] in ("hall", "room", "chamber") and t[1] == c[2]), raw
        L = [" ".join(c[2] if (k >= 1 and w == c[1] and (t[0] in ("link", "door", "secret") or k == 1)) else w for k, w in enumerate(t)) if (t := l.split()) and not l.startswith("#") else l for l in L]
    elif op == "fold":
        a, b = c[1], c[2]
        i = find(lambda t: len(t) > 1 and t[0] == "hall" and t[1] == a); assert len(i) == 1, raw
        del L[i[0]]
        out, seen = [], set()
        for l in L:
            t = l.split()
            if len(t) == 3 and t[0] in ("link", "door", "secret"):
                t = [t[0]] + [b if w == a else w for w in t[1:]]
                if t[1] == t[2]: continue
                l = " ".join(t)
            out.append(l)
        L = out
    else:
        raise SystemExit("bad op " + raw)
# drop duplicate edges
out, seen = [], set()
for l in L:
    t = l.split()
    if len(t) == 3 and t[0] in ("link", "door", "secret"):
        k = frozenset(t[1:])
        if k in seen: continue
        seen.add(k)
    out.append(l)
p.write_text("\n".join(out))
