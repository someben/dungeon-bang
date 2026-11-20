"""Strategy exploration for the Dungeon! sim, run in parallel.

  python explore.py uniform      # all four classes play the same strategy
  python explore.py profile      # one class switches strategy, the others play 'ev'
  python explore.py nash         # best-response rounds: each class picks its best strategy given the others
  python explore.py balance      # search strategy assignments for the most even win split
  python explore.py verify A,B,C,D [games]   # long run of one assignment (strategy names from STRATS)
  python explore.py rules        # house-rule tweaks one at a time, then a greedy search for the most even mix
  python explore.py adapt RULES  # under a rule mix, let each class switch to its best strategy
  python explore.py human [RULES ...]  # human-like styles: everyone the same style, then random mixed tables

Results are appended to results/explore.jsonl.
"""
import itertools, json, os, sys, time
from multiprocessing import Pool
from pathlib import Path

import sim

ROOT = Path(__file__).resolve().parent
CLASSES = ["rogue", "cleric", "fighter", "wizard"]
STRATS = {
    "ev": "ev",                         # best gold per turn of walking, any level
    "safe": "safe",                     # the board's 'safest levels' for the class
    "L1-2": "lv=1-2", "L1-3": "lv=1-3", "L2-4": "lv=2-4", "L3-5": "lv=3-5",
    "L4-6": "lv=4-6", "L5-6": "lv=5-6", "L6": "lv=6",
    "near": "dist=2.5",                 # nearest worthwhile room first
    "far": "dist=0.3",                  # biggest prize, almost regardless of distance
    "bold": "risk=0",                   # ignore what a hit-back would cost
    "cautious": "risk=3",               # avoid fights that put treasure at risk
    "scav": "scav=3",                   # chase treasure other heroes dropped
    "follow": "follow=1+scav=3",        # shadow the leader and pick up after them
    "chaos": "rand=1",                  # random target every time
    "eps": "rand=0.25",                 # mostly sensible, sometimes random
    "deep-bold": "lv=4-6+risk=0",
    "mid-bold": "lv=2-4+risk=0",
}
WIZ_ONLY = {
    "wiz-old": "spell_lv=1+min_lv=1+home_at=1+refill=99",  # spell anything, refill once, go home at 1 spell
    "wiz-min4": "min_lv=4",
    "wiz-min5": "min_lv=5",
}
BOOK = {"fireball": 0.7, "lightning": 0.3, "teleport": 0.0}
OUT = ROOT / "results" / "explore.jsonl"


def menu(cls):
    return list(STRATS) + (list(WIZ_ONLY) if cls == "wizard" else [])


def policy(name, cls):
    s = STRATS.get(name) or WIZ_ONLY[name]
    if cls == "wizard" and s.startswith("lv="):
        lo = s[3:].split("-")[0].split("+")[0]
        s += f"+min_lv={lo}"  # wizard's own deep-room filter follows the band
    return s


_B = _M = _T = None


def _chunk(args):
    global _B, _M, _T
    if _B is None:
        _B, _M, _T = sim.Board(), sim.load_monsters(), sim.load_treasures()
    pols, seed0, n, rules, book = args
    wins, rounds = [0] * 5, 0
    for g in range(seed0, seed0 + n):
        w, r = sim.Game(_B, _M, _T, CLASSES, pols, seed=g, book=book, max_rounds=400, rules=rules).play()
        wins[w.idx if w else 4] += 1
        rounds += r
    return wins, rounds


POOL = None


def run(names, games=1000, seed=0, rules=None, book=None):
    pols = [policy(nm, c) for nm, c in zip(names, CLASSES)]
    step = 25
    jobs = [(pols, seed * 10_000_000 + i, min(step, games - i), rules or {}, book or BOOK) for i in range(0, games, step)]
    wins, rounds = [0] * 5, 0
    for w, r in POOL.map(_chunk, jobs):
        wins = [a + b for a, b in zip(wins, w)]
        rounds += r
    res = {"strats": list(names), "rules": rules or {}, "book": book or BOOK, "games": games, "win": [w / games for w in wins[:4]],
           "none": wins[4] / games, "rounds": rounds / games}
    OUT.parent.mkdir(exist_ok=True)
    with open(OUT, "a") as f:
        f.write(json.dumps(res) + "\n")
    return res


def spread(res):
    return max(abs(w - 0.25) for w in res["win"])


def show(res, tag=""):
    w = "  ".join(f"{c[:3]} {x:5.1%}" for c, x in zip(CLASSES, res["win"]))
    print(f"{tag:<34} {w}   off-25% max {spread(res):5.1%}   rounds {res['rounds']:4.1f}"
          + (f"  unfinished {res['none']:.1%}" if res["none"] else ""), flush=True)


def uniform(games=2000):
    print("== everyone plays the same strategy")
    for s in STRATS:
        show(run([s] * 4, games, seed=1), s)


def profile(games=1000):
    print("== one class switches, the others play 'ev'")
    base = run(["ev"] * 4, games, seed=2)
    show(base, "baseline all ev")
    for i, c in enumerate(CLASSES):
        rows = []
        for s in menu(c):
            if s == "ev":
                continue
            names = ["ev"] * 4
            names[i] = s
            r = run(names, games, seed=2)
            rows.append((r["win"][i], s, r))
        rows.sort(reverse=True)
        print(f"-- {c} (ev wins {base['win'][i]:.1%})")
        for wi, s, r in rows:
            show(r, f"   {c} {s}")


def nash(games=800, rounds=1, start=None):
    cur = list(start or ["ev"] * 4)
    print("== best-response rounds, start", cur)
    for rd in range(rounds):
        changed = False
        for i, c in enumerate(CLASSES):
            best = None
            for s in menu(c):
                names = list(cur)
                names[i] = s
                r = run(names, games, seed=3 + rd)
                if best is None or r["win"][i] > best[0]:
                    best = (r["win"][i], s, r)
            if best[1] != cur[i]:
                changed = True
            cur[i] = best[1]
            show(best[2], f"round {rd + 1}: {c} -> {best[1]}")
        if not changed:
            print("stable: no class can do better by switching")
            break
    return cur


def balance(games=800, passes=3, starts=None):
    print("== search for the most even split (minimise the worst class's distance from 25%)")
    starts = starts or [["ev"] * 4]
    found = []
    for st in starts:
        cur = list(st)
        cur_r = run(cur, games, seed=5)
        show(cur_r, f"start {','.join(cur)}")
        for ps in range(passes):
            improved = False
            # move the class furthest from 25% first
            order = sorted(range(4), key=lambda i: -abs(cur_r["win"][i] - 0.25))
            for i in order:
                for s in menu(CLASSES[i]):
                    if s == cur[i]:
                        continue
                    names = list(cur)
                    names[i] = s
                    r = run(names, games, seed=5)
                    if spread(r) < spread(cur_r) - 0.005:
                        cur, cur_r, improved = names, r, True
                show(cur_r, f"pass {ps + 1} {CLASSES[i]}: {','.join(cur)}")
            if not improved:
                break
        found.append((spread(cur_r), cur))
    found.sort()
    return found


TWEAKS = {
    "roll 1 die to move": "move=d6",
    "roll 1 die + 2 to move": "move=d6p2",
    "failed secret search costs 1 space, roll again": "secret=retry",
    "found secret doors open for everyone": "secret_share=1",
    "regain spells in any cleared chamber": "regen_where=chamber",
    "regain the whole spellbook": "regen_amt=full",
    "regaining spells doesn't cost a turn": "regen_wait=0",
    "missed spell goes back in hand": "miss_keep=1",
    "Wizard always starts with 12 spells": "book=12",
    "Teleport to any chamber or Great Hall": "tele_range=6",
    "Teleport from any space": "tele_from=any",
    "Teleport card is kept": "tele_keep=1",
    "only Fighters wield Magic Swords": "swords=fighter",
    "win needs a Treasure from your deepest safe level": "trophy=1",
}
TELE_BOOKS = [BOOK, {"fireball": 0.55, "lightning": 0.25, "teleport": 0.2},
              {"fireball": 0.45, "lightning": 0.2, "teleport": 0.35}]


def rules_of(text):
    return sim.parse_rules(text)


def run_rules(text, games, seed, names=None):
    """Run a rule mix; if Teleport is in play, the Wizard picks whichever spellbook mix wins it most."""
    names = names or ["ev"] * 4
    books = TELE_BOOKS if "tele" in text else [BOOK]
    best = None
    for bk in books:
        r = run(names, games, seed=seed, rules=rules_of(text), book=bk)
        if best is None or r["win"][3] > best["win"][3]:
            best = r
    return best


def rules_search(games=4000, singles=True):
    base = run_rules("", games, 11)
    if singles:
        print("== one house rule at a time (everyone plays 'ev')")
        show(base, "printed rules")
        for name, t in TWEAKS.items():
            show(run_rules(t, games, 11), name[:34])
    print("== greedy: keep adding the rule that most evens the split")
    cur, cur_r = [], run_rules("", games // 2, 12)
    while True:
        best = None
        for name, t in TWEAKS.items():
            if t in cur or any(t.split("=")[0] == c.split("=")[0] for c in cur):
                continue
            r = run_rules("+".join(cur + [t]), games // 2, 12)
            if best is None or spread(r) < spread(best[1]):
                best = (t, r)
        if best is None or spread(best[1]) > spread(cur_r) - 0.01:
            break
        cur, cur_r = cur + [best[0]], best[1]
        show(cur_r, "+ " + best[0])
    print("best mix:", "+".join(cur) or "(none)")
    return cur


def adapt(text, games=1000):
    """Each class in turn switches to its best strategy (others keep theirs) under the rule mix."""
    cur = ["ev"] * 4
    print(f"== adapt under {text}")
    show(run_rules(text, 4000, 13, cur), "all ev")
    for rd in range(2):
        changed = False
        for i, c in enumerate(CLASSES):
            best = None
            for st in menu(c):
                names = list(cur)
                names[i] = st
                r = run_rules(text, games, 14 + rd, names)
                if best is None or r["win"][i] > best[0]:
                    best = (r["win"][i], st)
            if best[1] != cur[i]:
                cur[i], changed = best[1], True
        show(run_rules(text, 4000, 15 + rd, cur), f"round {rd + 1}: {','.join(cur)}")
        if not changed:
            break
    return cur


# Human-like play styles: all guess at the odds a little (noise), each has a different habit.
HUMAN = {
    "casual": "noise=0.5",                              # sensible, but judges by gut feel
    "by-the-board": "safe+noise=0.3",                   # sticks to the board's 'safest levels' for the class
    "ladder": "ladder=1+noise=0.3",                     # starts shallow, goes deeper as the gold piles up
    "nearest": "dist=2.5+noise=0.3",                    # whatever worthwhile room is closest
    "big-game": "dist=0.5+risk=0.5+noise=0.3",          # walks far for the big prizes
    "timid": "risk=3+noise=0.3",                        # won't risk the treasure already held
    "reckless": "risk=0+noise=0.3",                     # never thinks about getting hit back
    "wanderer": "rand=0.3+noise=0.3",                   # often just goes somewhere
    "vulture": "scav=3+follow=0.5+noise=0.3",           # hangs around the leader for dropped loot
}
HUMAN_WIZ = {"spell-happy": "spell_lv=1+min_lv=1+home_at=1+noise=0.3"}  # casts at everything, heads home early


def human_menu(cls):
    return list(HUMAN) + (list(HUMAN_WIZ) if cls == "wizard" else [])


def _mixed(args):
    """Games where every seat draws a random human style; returns per (class, style) seats and wins."""
    global _B, _M, _T
    if _B is None:
        _B, _M, _T = sim.Board(), sim.load_monsters(), sim.load_treasures()
    seed0, n, rules = args
    import random
    seats, wins, rounds = {}, {}, 0
    for g in range(seed0, seed0 + n):
        r = random.Random(g * 7 + 1)
        names = [r.choice(human_menu(c)) for c in CLASSES]
        pols = [HUMAN.get(nm) or HUMAN_WIZ[nm] for nm in names]
        w, rd = sim.Game(_B, _M, _T, CLASSES, pols, seed=g, book=BOOK, max_rounds=400, rules=rules).play()
        rounds += rd
        for c, nm in zip(CLASSES, names):
            seats[c, nm] = seats.get((c, nm), 0) + 1
        k = ("win", w.cls, names[w.idx]) if w else ("none",)
        wins[k] = wins.get(k, 0) + 1
    return seats, wins, rounds


def human(rule_sets, games=3000, mixed_games=24000):
    for text in rule_sets:
        rules = rules_of(text)
        label = text or "printed rules"
        print(f"\n#### {label}")
        print("== everyone plays the same human style")
        for st in HUMAN:
            names = [st] * 4
            pols = [HUMAN[st]] * 4
            step = 25
            jobs = [(pols, 31 * 10_000_000 + i, min(step, games - i), rules, BOOK) for i in range(0, games, step)]
            wins, rd = [0] * 5, 0
            for w, r in POOL.map(_chunk, jobs):
                wins = [a + b for a, b in zip(wins, w)]
                rd += r
            res = {"strats": names, "human": True, "rules": rules, "games": games,
                   "win": [x / games for x in wins[:4]], "none": wins[4] / games, "rounds": rd / games}
            with open(OUT, "a") as f:
                f.write(json.dumps(res) + "\n")
            show(res, st)
        print(f"== mixed tables: every seat picks a random human style ({mixed_games} games)")
        seats, wins, rd = {}, {}, 0
        for sts, ws, r in POOL.map(_mixed, [(32 * 10_000_000 + i, 50, rules) for i in range(0, mixed_games, 50)]):
            for k, v in sts.items():
                seats[k] = seats.get(k, 0) + v
            for k, v in ws.items():
                wins[k] = wins.get(k, 0) + v
            rd += r
        tot = [sum(v for k, v in wins.items() if k[0] == "win" and k[1] == c) / mixed_games for c in CLASSES]
        res = {"strats": ["human-mix"] * 4, "human": True, "rules": rules, "games": mixed_games, "win": tot,
               "none": wins.get(("none",), 0) / mixed_games, "rounds": rd / mixed_games}
        with open(OUT, "a") as f:
            f.write(json.dumps(res) + "\n")
        show(res, "MIXED TABLE overall")
        print("   win rate by the style a class played (vs random opponents):")
        for c in CLASSES:
            row = sorted(((wins.get(("win", c, st), 0) / seats[c, st], st) for st in human_menu(c)), reverse=True)
            print(f"   {c:8}" + "  ".join(f"{st} {x:.0%}" for x, st in row))


def main():
    global POOL
    POOL = Pool(os.cpu_count())
    t = time.time()
    cmd = sys.argv[1]
    if cmd == "uniform":
        uniform()
    elif cmd == "profile":
        profile()
    elif cmd == "nash":
        nash(start=sys.argv[2].split(",") if len(sys.argv) > 2 else None, rounds=int(sys.argv[3]) if len(sys.argv) > 3 else 1)
    elif cmd == "balance":
        starts = [a.split(",") for a in sys.argv[2:]] or None
        for sp, names in balance(starts=starts):
            print(f"best found: {','.join(names)}  (worst class {sp:.1%} off 25%)")
    elif cmd == "rules":
        rules_search()
    elif cmd == "greedy":
        rules_search(games=int(sys.argv[2]) if len(sys.argv) > 2 else 6000, singles=False)
    elif cmd == "adapt":
        adapt(sys.argv[2] if len(sys.argv) > 2 else "")
    elif cmd == "human":
        human(sys.argv[2:] or ["", "swords=fighter+book=12"])
    elif cmd == "verify":
        n = int(sys.argv[3]) if len(sys.argv) > 3 else 10000
        show(run(sys.argv[2].split(","), n, seed=9), f"verify {sys.argv[2]}")
    print(f"[{time.time() - t:.0f}s]")


if __name__ == "__main__":
    main()
