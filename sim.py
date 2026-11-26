"""Dungeon! (2014 WotC edition) Monte Carlo simulator.

Rules: rules.md. Data: monsters.csv, treasures.csv, board.txt (traced board graph).

  python sim.py --games 2000 --lineup rogue,cleric,fighter,wizard
  python sim.py --games 2000 --lineup fighter --policy safe        # solo
  python sim.py --games 1 --lineup rogue,wizard --verbose           # watch one game

Policies:
  ev    pick the target with the best expected gp per turn (risk-aware), any level
  safe  same, but only target rooms/chambers in the board's "safest levels" for the class
"""
import argparse, csv, heapq, math, random, sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
from board import parse as parse_board  # noqa: E402

CLASSES = ("rogue", "cleric", "fighter", "wizard")
GOAL = {"rogue": 10000, "cleric": 10000, "fighter": 20000, "wizard": 30000}
SAFE_LEVELS = {"rogue": (1, 3), "cleric": (2, 4), "fighter": (3, 5), "wizard": (4, 6)}
MOVE = 5
# Wizard play style (tunable with --wiz key=val,...):
#   spell_lv   only spend Fireball/Lightning on monsters of this level or deeper (melee below it)
#   min_lv     while holding attack spells, only head for rooms of this level or deeper
#   home_at    walk back to the Great Hall when attack spells drop to this many
#   refill     keep rolling in the Great Hall until within this many spells of a full book (99 = one roll only)
WIZ = {"spell_lv": 4, "min_lv": 6, "home_at": 0, "refill": 0}
SLIDE_LEVEL = 4
NUM_SLOTS = 12  # numbered monster slots on the board edge
# House-rule switches (Game(rules={...}) or --rules key=val,...). Defaults are the printed 2014 rules.
#   move         "5" fixed 5 spaces | "d6" roll 1 die | "d6p2" roll 1 die and add 2
#   secret       "std" a failed search ends the move | "retry" a failed search costs 1 space and you may roll again
#   secret_share False | True: a secret door found by anyone is open for everyone
#   regen_where  "gh" Great Hall only | "chamber" the Great Hall or any cleared chamber
#   regen_amt    "d6" up to 1 die of spells back | "full" the whole book back
#   regen_wait   True: spells come back at the start of the next turn (which it uses up) | False: at once
#   miss_keep    False | True: a Fireball/Lightning that misses from outside goes back into the hand
#   book         "d6+6" | "12": every Wizard starts with 12 spells
#   tele_range   1: Teleport reaches chambers within 1 level | 6: any chamber, Great Hall included
#   tele_from    "chamber" | "any": cast Teleport from any space
#   tele_keep    False | True: Teleport goes back into the hand after use
#   swords       "all" | "fighter": only Fighters can wield Magic Swords (others still keep the gp)
#   trophy       False | True: to win you also need a Treasure from the deepest of your 'safest levels'
#   f_reroll     False | True: once per fight a Fighter may re-roll a missed attack
#   f_armor      False | True: a Fighter treats Stunned (6-7) as a Miss
#   f_tough      False | True: a Hurt Fighter doesn't lose a turn
#   f_move       False | True: a Fighter moves up to 6 spaces
#   drop_pick    which Treasure cards a "drop 1 random" / "drop half" result takes (Crushed drops everything):
#                "random" truly random | "die" roll 1 die and count along the hand, laid face up in the order
#                collected (wrapping) | "left" the player on your left picks by card back: the deepest level |
#                "newest" your most recently collected | "lowest" your lowest-level card |
#                "choice" you pick: your cheapest cards, keeping your wielded Magic Sword, ESP, Crystal Ball,
#                and Secret Door cards for last (every class, for both the 1-card and the half drop)
#   rest_move    lose=rest: the most spaces a resting Hero moves (0-5)
#   rest_fight   lose=rest: False | True: a resting Hero may still fight or cast
#   clear_perk   "none" | "deeper": whoever defeats the last monster in a level's rooms (chambers don't count)
#                draws 1 Treasure card from the next level down (that level's own pile is empty by then) |
#                "shallow" the same, but only for a level shallower than your class's printed safest levels |
#                "tokens" the clearer gives back all their Hourglass tokens
#   hourglass    lose=hourglass: when Hourglass tokens go: "next" after your next attack roll | "win" when you
#                win a fight | "hall" when you end a turn in the Great Hall | "winhall" either one | "win1" each win takes 1 off | "game" never (Crushed clears everything)
#   goal_<class> gold needed to win for that class (0 = printed: 10000 / 10000 / 20000 / 30000)
#   stun         "drop" Stunned drops 1 Treasure card | "token" Stunned gives 1 Hourglass token instead
#   chamber_perk False | True: the 3rd Defeated token on a chamber earns a Treasure card of its level
#   deep_pick    0 | N: in a room of level N or deeper, draw 2 Treasure cards, keep 1, the other to the bottom
#   homeward     False | True: once you have enough gold to win, you move 10 spaces a turn
#   underdog     False | True: the Hero(es) with the smallest share of their gold goal get +1 on attack rolls
#   crush        "all" Crushed drops everything | "half" Crushed drops half (your choice), still back to the Hall
#   shortcut     False | True: from the Great Hall, move straight to any fully cleared chamber (or back) as your
#                whole move
#   serious      "hall" Seriously Hurt sends you to the Great Hall | "tokens" drop half, take 2 Hourglass tokens,
#                and step back 1 space instead
#   flee         False | True: having seen the monster, you may step back out by taking 1 Hourglass token
#   shallow      a win in a room shallower than your class's printed safest levels: "none" no effect |
#                "token" you take an Hourglass token | "notreasure" you draw no Treasure card (dropped cards still yours)
#   daring       False | True: +1 on attack rolls in a room or chamber deeper than your class's safest levels
#   lose         what replaces each lost turn (Hurt 8-10: 1; Cage Trap: 1 or 2):
#                "turn" lose the turn | "wound" -1 on your next attack roll (tokens stack) |
#                "knock" knocked back 5 spaces toward the Great Hall | "limp" next turn move but don't fight |
#                "slow" next turn move only 2 | "extra" drop 1 more Treasure card | "rush" every opponent moves 2 |
#                "rest" next turn you rest: move at most rest_move spaces, and fight or cast only if rest_fight |
#                "shaken" +1 on the monster's fight-back roll in your next fight |
#                "bless" every opponent gets +1 on their next attack roll |
#                "hourglass" take an Hourglass token: -1 per token on your attack rolls (spells too) until
#                the tokens go, per the 'hourglass' rule |
#                "bounty" whoever beats the monster that hurt you draws 1 extra Treasure card of its level
RULES = {"move": "5", "secret": "std", "secret_share": False, "regen_where": "gh", "regen_amt": "d6",
         "regen_wait": True, "miss_keep": False, "book": "d6+6", "tele_range": 1, "tele_from": "chamber",
         "tele_keep": False, "swords": "all", "trophy": False,
         "f_reroll": False, "f_armor": False, "f_tough": False, "f_move": False,
         "drop_pick": "random", "lose": "turn", "rest_move": 2, "rest_fight": False, "clear_perk": "none", "hourglass": "win",
         "goal_rogue": 0, "goal_cleric": 0, "goal_fighter": 0, "goal_wizard": 0,
         "stun": "drop", "chamber_perk": False, "deep_pick": 0, "homeward": False, "underdog": False,
         "crush": "all", "shortcut": False, "serious": "hall", "flee": False, "shallow": "none", "daring": False}
# fight-back table probabilities (2d6)
P2 = {s: (6 - abs(s - 7)) / 36 for s in range(2, 13)}


def parse_policy(policy, cls):
    """Strategy string -> settings. 'ev' (default), 'safe', or '+'-joined key=val pairs:
      lv=A-B     only go for rooms on levels A..B (known monsters / dropped loot always allowed)
      risk=K     weight on expected treasure lost when a monster hits back (0 = bold, 3 = cautious)
      dist=E     score = value / turns**E (0 = chase the biggest prize anywhere, 2+ = nearest first)
      rand=P     chance each new target is picked at random instead (1 = pure chaos)
      scav=W     weight on treasure other heroes dropped (3 = scavenger)
      follow=W   prefer targets near the hero closest to winning (shadow the leader)
      noise=S    misjudge each target's worth by a random factor exp(N(0,S)) (human guesswork)
      ladder=1   start shallow and go deeper as treasure piles up, across the class's 'safest levels'
      spell_lv, min_lv, home_at, refill   Wizard play style (see WIZ)
    """
    p = {"lo": 1, "hi": 6, "risk": 1.0, "dist": 1.0, "rand": 0.0, "scav": 1.0, "follow": 0.0,
         "noise": 0.0, "ladder": 0.0, "wiz": dict(WIZ)}
    for part in filter(None, policy.split("+")):
        if part == "ev":
            continue
        if part == "safe":
            p["lo"], p["hi"] = SAFE_LEVELS[cls]
            continue
        k, v = part.split("=")
        if k == "lv":
            a, _, b = v.partition("-")
            p["lo"], p["hi"] = int(a), int(b or a)
        elif k in ("risk", "dist", "rand", "scav", "follow", "noise", "ladder"):
            p[k] = float(v)
        elif k in WIZ:
            p["wiz"][k] = int(v)
        else:
            raise ValueError(f"unknown strategy setting {part!r}")
    return p


def d6(rng):
    return rng.randint(1, 6)


def two_d6(rng):
    return rng.randint(1, 6) + rng.randint(1, 6)


def p_at_least(t):
    """P(2d6 >= t)."""
    return sum(p for s, p in P2.items() if s >= t)


# ---------------------------------------------------------------- data

def load_monsters():
    out = []
    with open(ROOT / "monsters.csv") as f:
        for i, r in enumerate(csv.DictReader(f)):
            tgt = {}
            for k in ("rogue", "cleric", "fighter", "wizard", "fireball", "lightning"):
                v = r[k].strip()
                tgt[k] = None if v in ("", "-") else int(v)
            out.append(dict(id=i, level=int(r["level"]), name=r["name"], tgt=tgt, trap=r["trap"].strip() or None))
    return out


def load_treasures():
    out = []
    with open(ROOT / "treasures.csv") as f:
        for i, r in enumerate(csv.DictReader(f)):
            eff = r["effect"].strip() or None
            sword = None
            if eff and eff.startswith("sword:"):
                sword = []  # list of (lo, hi, bonus)
                for part in eff[6:].split(";"):
                    rng_, b = part.split("=")
                    lo, hi = map(int, rng_.split("-")) if "-" in rng_ else (int(rng_), int(rng_))
                    sword.append((lo, hi, int(b)))
                eff = "sword"
            out.append(dict(id=i, level=int(r["level"]), name=r["name"], gp=int(r["gp"]), effect=eff, sword=sword))
    return out


class Board:
    def __init__(self):
        nodes, edges = parse_board(ROOT / "board.txt")
        self.nodes = nodes
        self.adj = defaultdict(list)  # node -> [(nbr, kind)]
        for a, b, k in edges:
            self.adj[a].append((b, k))
            self.adj[b].append((a, k))
        self.gh = next(n for n, v in nodes.items() if v["kind"] == "chamber" and v["level"] == 0)
        self.rooms = [n for n, v in nodes.items() if v["kind"] == "room"]
        self.chambers = [n for n, v in nodes.items() if v["kind"] == "chamber" and v["level"] > 0]

    def kind(self, n):
        return self.nodes[n]["kind"]

    def level(self, n):
        return self.nodes[n]["level"]


# ---------------------------------------------------------------- game state

class Hero:
    def __init__(self, idx, cls, policy, book):
        self.idx, self.cls, self.policy = idx, cls, policy
        self.p = parse_policy(policy, cls)
        self.wiz = self.p["wiz"]
        self.book = dict(book)  # starting spellbook (for Crushed rebuild and regen cap)
        self.reset()
        self.stats = Counter()

    def reset(self):
        self.pos = None
        self.prev = None
        self.cards = []
        self.lose = 0
        self.wound = 0  # lose=wound: -1 per token on the next attack roll
        self.limp = 0   # lose=limp: turns of moving without fighting
        self.slow = 0   # lose=slow: turns of moving only 2
        self.resting = 0  # lose=rest: turns of resting (limited moves, maybe no fighting)
        self.hourglass = 0  # lose=hourglass: tokens, -1 each on attack rolls
        self.shaken = 0  # lose=shaken: + on the fight-back roll in the next fight
        self.found = set()  # frozenset({a,b}) secret doors found
        self.sword_card = None
        self.sword_bonus = 0
        self.spells = dict(self.book)
        self.regen = False
        self.goal = None
        self.cast_this_turn = False  # rulebook: only 1 Spell card per turn

    @property
    def gp(self):
        return sum(c["gp"] for c in self.cards)

    def has(self, eff):
        return any(c["effect"] == eff for c in self.cards)

    def nspells(self):
        return sum(self.spells.values())

    def attack_spells(self):
        return self.spells.get("fireball", 0) + self.spells.get("lightning", 0)

    def maxspells(self):
        return sum(self.book.values())


class Game:
    def __init__(self, board, monsters, treasures, lineup, policy="ev", seed=None, verbose=False,
                 book=None, max_rounds=1000, rules=None):
        self.b, self.rng, self.verbose = board, random.Random(seed), verbose
        self.R = dict(RULES)
        for k, v in (rules or {}).items():
            assert k in RULES, k
            self.R[k] = v
        self.found_all = set()  # secret doors anyone has found (used with secret_share)
        self.stats_slots_full = 0
        self.max_rounds = max_rounds
        self.mdeck = defaultdict(list)
        self.mdisc = defaultdict(list)
        self.all_monsters = defaultdict(list)
        for m in monsters:
            self.mdeck[m["level"]].append(m)
            self.all_monsters[m["level"]].append(m)
        for lv in self.mdeck:
            self.rng.shuffle(self.mdeck[lv])
        self.tdeck = defaultdict(list)
        for t in treasures:
            self.tdeck[t["level"]].append(t)
        for lv in self.tdeck:
            self.rng.shuffle(self.tdeck[lv])
        self.defeated = Counter()     # node -> defeated tokens
        # node -> {"monster": card, "drops": [cards], "known": None (face up) or {hero idx who peeked},
        #          "treasure": card pre-drawn by a Crystal Ball (rooms), else absent}
        self.slot = {}
        self.heroes = []
        # spell deck and books (alternate picks between wizards)
        self.want = book or {"fireball": 0.5, "lightning": 0.5, "teleport": 0.0}
        wiz = [i for i, c in enumerate(lineup) if c == "wizard"]
        books = self.build_books(wiz, {"fireball": 9, "lightning": 9, "teleport": 6})
        for i, c in enumerate(lineup):
            self.heroes.append(Hero(i, c, policy[i] if isinstance(policy, (list, tuple)) else policy, books.get(i, {})))
        for h in self.heroes:
            h.pos = board.gh
        # per-level unknown-monster win probabilities, precomputed from full deck composition
        self.p_level = {}
        for lv, deck in self.mdeck.items():
            for mode in ("rogue", "cleric", "fighter", "wizard", "fireball", "lightning"):
                for bonus in (0, 1, 2):
                    ps = [1.0 if m["trap"] else self.p_hit(m, mode, bonus) for m in deck]
                    self.p_level[lv, mode, bonus] = sum(ps) / len(ps)
        self.avg_treasure = {lv: sum(t["gp"] for t in d) / len(d) for lv, d in self.tdeck.items()}

    def build_books(self, wiz, pool):
        """Each listed Wizard rolls 1d6+6 and they take turns picking 1 Spell card at a time from pool."""
        books = {i: Counter() for i in wiz}
        sizes = {i: 12 if self.R["book"] == "12" else d6(self.rng) + 6 for i in wiz}
        want = self.want
        while any(sum(books[i].values()) < sizes[i] for i in wiz) and sum(pool.values()):
            for i in wiz:
                if sum(books[i].values()) >= sizes[i]:
                    continue
                n = sum(books[i].values()) + 1
                # pick the spell furthest below its target share that is still in the pool
                choices = [s for s in pool if pool[s] > 0]
                if not choices:
                    break
                s = max(choices, key=lambda s: want.get(s, 0) * n - books[i][s])
                books[i][s] += 1
                pool[s] -= 1
        return books

    def new_wizard_book(self, h):
        """A Crushed Wizard comes back as a new Wizard with a new spellbook, picked from the Spell cards
        that aren't in another Wizard's book."""
        pool = {"fireball": 9, "lightning": 9, "teleport": 6}
        for o in self.heroes:
            if o is not h and o.cls == "wizard":
                for k, v in o.book.items():
                    pool[k] -= v
        h.book = dict(self.build_books([h.idx], pool)[h.idx])

    def park(self, n, h=None):
        """House ruling (user, 2026-11-20): a monster that wasn't defeated (after a fight, a missed spell, or an
        ESP peek) takes a numbered slot if one of the 12 is free. If all 12 are taken it is discarded, and any
        treasure dropped in that fight goes under a waiting monster of the dropping player's choice.
        A discarded monster's space stays undefeated, so the next hero in draws a new card from that level."""
        s = self.slot.get(n)
        if not s or len(self.slot) <= NUM_SLOTS:
            return
        del self.slot[n]
        self.mdisc[s["monster"]["level"]].append(s["monster"])
        if s.get("treasure"):  # a Crystal Ball's face-down treasure goes back into its pile
            lv = self.b.level(n)
            self.tdeck[lv].insert(self.rng.randrange(len(self.tdeck[lv]) + 1), s["treasure"])
        self.stats_slots_full += 1
        self.log(f"  all {NUM_SLOTS} slots taken: {s['monster']['name']} in {n} is discarded")
        if s["drops"] or s.get("bounty"):
            to = self.choose_drop_slot(h)
            self.slot[to]["drops"].extend(s["drops"])
            if s.get("bounty"):  # the bounty goes with the dropped treasure
                self.slot[to]["bounty"] = self.slot[to].get("bounty", 0) + s["bounty"]
            self.log(f"    its {len(s['drops'])} dropped card(s) go under the monster in {to}")

    def choose_drop_slot(self, h):
        """Player's choice: under the waiting monster this hero is likeliest to beat soonest."""
        dist, _ = self.dijkstra(h)
        def score(m):
            p = self.best_mode(h, self.seen_monster(h, self.slot[m]), self.b.level(m))[0]
            return p / (1 + math.ceil(dist.get(m, 1e9) / MOVE))
        return max(self.slot, key=score)

    def goal(self, h):
        return self.R["goal_" + h.cls] or GOAL[h.cls]

    def log(self, *a):
        if self.verbose:
            print(*a)

    # ---------- combat helpers
    @staticmethod
    def p_hit(m, mode, bonus):
        t = m["tgt"][mode]
        if t is None:
            if bonus and mode not in ("fireball", "lightning"):
                t = 13
            else:
                return 0.0
        return p_at_least(t - bonus) if mode not in ("fireball", "lightning") else p_at_least(t)

    def p_hit_melee(self, h, s, n):
        return self.best_mode(h, self.seen_monster(h, s), self.b.level(n), spells=False)[0]

    def modes(self, h):
        ms = [h.cls]
        if h.cast_this_turn:
            return ms
        for s in ("fireball", "lightning"):
            if h.spells.get(s, 0) > 0:
                ms.append(s)
        return ms

    def best_mode(self, h, m=None, level=None, spells=True):
        """Return (p, mode) of the best available attack vs a known monster m or an unknown one of a level."""
        best = (-1, None)
        if spells and (m["level"] if m else level) < h.wiz["spell_lv"]:
            spells = False
        lv = m["level"] if m else level
        for mode in (self.modes(h) if spells else [h.cls]):
            bonus = h.sword_bonus if mode == h.cls else 0
            if self.atk_minus(h, lv):
                p = self.p_wounded(h, m, level, mode, bonus)
            else:
                p = self.p_hit(m, mode, bonus) if m else self.p_level[level, mode, bonus]
            if mode == "fighter" and self.R["f_reroll"]:
                p = 1 - (1 - p) ** 2
            # prefer melee on ties (spells are a resource)
            if p > best[0] + (0.02 if mode != h.cls else 0):
                best = (p, mode)
        return best

    def p_wounded(self, h, m, level, mode, bonus):
        """Hit chance with h.wound off the roll, vs a known monster or the average of the level's deck."""
        def one(m):
            if m["trap"]:
                return 1.0
            t = m["tgt"][mode]
            if t is None:
                if not bonus or mode in ("fireball", "lightning"):
                    return 0.0
                t = 13
            return p_at_least(t - (bonus if mode not in ("fireball", "lightning") else 0) + self.atk_minus(h, m["level"] if m else level))
        if m:
            return one(m)
        deck = self.all_monsters[level]
        return sum(one(x) for x in deck) / len(deck)

    def draw_monster(self, lv):
        if not self.mdeck[lv]:
            self.mdeck[lv] = self.mdisc[lv]
            self.mdisc[lv] = []
            self.rng.shuffle(self.mdeck[lv])
        if not self.mdeck[lv]:
            # every card of this level is waiting unbeaten on the board; the rules don't cover this,
            # so draw a duplicate of a random card of that level rather than stall
            return dict(self.rng.choice(self.all_monsters[lv]))
        return self.mdeck[lv].pop()

    def draw_treasure(self, lv):
        return self.tdeck[lv].pop() if self.tdeck[lv] else None

    # ---------- board helpers
    def cleared(self, n):
        k = self.b.kind(n)
        if k == "room":
            return self.defeated[n] >= 1
        if k == "chamber":
            return self.b.level(n) == 0 or self.defeated[n] >= 3
        return True

    def occupied(self, n, me):
        return any(o is not me and o.pos == n for o in self.heroes)

    def can_cross(self, h, a, b, kind):
        if kind != "secret" or h.has("secret_door"):
            return True
        k = frozenset((a, b))
        return k in h.found or (self.R["secret_share"] and k in self.found_all)

    def dijkstra(self, h):
        """Distances from h.pos. Stoppers (uncleared rooms/chambers) can be reached but cost a turn to pass.
        Unknown secret doors cost extra (expected failed attempts). Returns dist, parent."""
        p_find = 4 / 6 if h.cls == "rogue" else 2 / 6
        # expected cost of failed searches: a whole turn each, or 1 space each under 'retry'
        secret_pen = (1 if self.R["secret"] == "retry" else MOVE) * (1 / p_find - 1)
        dist = {h.pos: 0.0}
        par = {h.pos: None}
        pq = [(0.0, h.pos)]
        while pq:
            d, n = heapq.heappop(pq)
            if d > dist[n]:
                continue
            leave = 0.0
            if n != h.pos and not self.cleared(n):
                # must fight here before passing; a chamber holds up to 3 monsters
                left = 3 - self.defeated[n] if self.b.kind(n) == "chamber" else 1
                leave = MOVE * 1.5 * left
            for m, kind in self.b.adj[n] + self.portals(n):
                c = (MOVE if kind == "portal" else 1) + leave
                if kind == "secret" and not self.can_cross(h, n, m, kind):
                    c += secret_pen
                nd = d + c
                if nd < dist.get(m, 1e18):
                    dist[m] = nd
                    par[m] = n
                    heapq.heappush(pq, (nd, m))
        return dist, par

    def portals(self, n):
        """shortcut: the Great Hall links to every fully cleared chamber, one whole move each way."""
        if not self.R["shortcut"]:
            return []
        if n == self.b.gh:
            return [(c, "portal") for c in self.b.chambers if self.cleared(c)]
        if self.b.kind(n) == "chamber" and self.cleared(n):
            return [(self.b.gh, "portal")]
        return []

    @staticmethod
    def path_to(par, t):
        p = []
        while t is not None:
            p.append(t)
            t = par[t]
        return p[::-1]

    # ---------- decisions
    def fight_back_loss(self, h):
        gp = h.gp
        card = self.first_drop_value(h)
        q = {r: 0.0 for r in range(2, 13)}  # fight-back results, after a Shaken bonus
        for r, pr in P2.items():
            q[min(12, r + h.shaken)] += pr
        loss = gp * q[12] + gp * 0.5 * q[11] + card * (1 - q[12] - q[11] - sum(q[s] for s in range(2, 6)))
        if self.R["lose"] == "extra" and not (h.cls == "fighter" and self.R["f_tough"]):
            loss += card * (P2[8] + P2[9] + P2[10])
        return loss

    def first_drop_value(self, h):
        """Expected gp of the first card a 1-card drop takes, under drop_pick."""
        c = h.cards
        if not c:
            return 0
        how = self.R["drop_pick"]
        if how == "newest":
            return c[-1]["gp"]
        if how == "die":
            return sum(c[(r - 1) % len(c)]["gp"] for r in range(1, 7)) / 6
        if how == "choice":
            return self.choice_order(h)[0]["gp"]
        if how in ("left", "lowest"):
            lv = (max if how == "left" else min)(x["level"] for x in c)
            pick = [x["gp"] for x in c if x["level"] == lv]
            return sum(pick) / len(pick)
        return sum(x["gp"] for x in c) / len(c)

    def seen_monster(self, h, s):
        """The slot's monster card if h can see it: face up, or h peeked at it (ESP / Crystal Ball)."""
        if not s:
            return None
        k = s.get("known")
        return s["monster"] if k is None or h.idx in k else None

    def room_treasure_value(self, h, n, s):
        lv = self.b.level(n)
        if self.b.kind(n) != "room":
            return 0
        if self.R["shallow"] == "notreasure" and lv < SAFE_LEVELS[h.cls][0]:
            return 0
        t = s.get("treasure") if s else None
        if t is not None:
            return t["gp"] if h.idx in (s.get("known") or ()) or s.get("known") is None else self.avg_treasure.get(lv, 0)
        return self.avg_treasure.get(lv, 0) if self.tdeck[lv] else 0

    def target_value(self, h, n):
        """(expected gain, p_win) for fighting at node n, using only what h can see."""
        lv = self.b.level(n)
        s = self.slot.get(n)
        drops = sum(c["gp"] for c in s["drops"]) if s else 0  # dropped loot lies face up
        gain = drops * h.p["scav"] + self.room_treasure_value(h, n, s)
        if s and s.get("bounty"):
            gain += s["bounty"] * self.avg_treasure.get(lv, 0)
        p, mode = self.best_mode(h, self.seen_monster(h, s), lv)
        loss = 0 if mode in ("fireball", "lightning") else self.fight_back_loss(h) * h.p["risk"]
        return p * gain - (1 - p) * loss, p

    def leader_dist(self, h):
        """Unweighted step distances from the opponent closest to winning (for 'follow')."""
        others = [o for o in self.heroes if o is not h]
        if not others:
            return None
        lead = max(others, key=lambda o: o.gp / self.goal(o))
        d = {lead.pos: 0}
        q = [lead.pos]
        for x in q:
            for y, _ in self.b.adj[x]:
                if y not in d:
                    d[y] = d[x] + 1
                    q.append(y)
        return d

    def choose_target(self, h):
        dist, par = self.dijkstra(h)
        goal = self.goal(h)
        lo, hi = h.p["lo"], h.p["hi"]
        if not self.has_trophy(h):
            need = SAFE_LEVELS[h.cls][1]
            if h.gp >= goal * 0.6:
                lo, hi = max(lo, need), 6  # enough gold for now: go get the trophy
        elif h.gp >= goal:
            return self.b.gh, dist, par
        if h.cls == "wizard" and h.maxspells() and h.attack_spells() <= h.wiz["home_at"] and not self.refill_spot(h.pos):
            spots = [n for n in [self.b.gh] + self.b.chambers if n in dist and self.refill_spot(n)]
            return min(spots, key=lambda n: dist[n]), dist, par
        if h.p["ladder"]:
            # aim level climbs through the class's safest levels as gold approaches the goal
            slo, shi = SAFE_LEVELS[h.cls]
            t = round(slo - 0.5 + min(1.0, h.gp / goal) * (shi - slo + 1))
            lo, hi = max(lo, max(1, t - 1)), min(hi, min(6, t + 1))
            lo = min(lo, hi)
        g = h.goal
        if g and g != h.pos and g in dist and not self.cleared(g) and self.target_value(h, g)[0] > 0:
            return g, dist, par
        ld = self.leader_dist(h) if h.p["follow"] else None
        bt, fbt, cands = self.scan_targets(h, dist, ld, lo, hi)
        if bt is None and (lo, hi) != (1, 6):
            # the preferred levels have nothing worth taking any more: widen to the whole dungeon
            bt, fbt, cands = self.scan_targets(h, dist, ld, 1, 6)
        if cands and h.p["rand"] and self.rng.random() < h.p["rand"]:
            bt = self.rng.choice(cands)
        if bt is None:
            bt = fbt or self.b.gh
        h.goal = bt if bt != self.b.gh else None
        return bt, dist, par

    def scan_targets(self, h, dist, ld, lo, hi):
        best, bt = -1e18, None
        fb, fbt = -1e18, None  # least-bad target, used only when nothing has positive value
        cands = []
        for n in self.b.rooms + self.b.chambers:
            if self.cleared(n) or n not in dist:
                continue
            if self.occupied(n, h) and self.b.kind(n) == "room":
                continue
            lv = self.b.level(n)
            ev, p = self.target_value(h, n)
            if not (lo <= lv <= hi) and not self.slot.get(n):
                continue
            if h.cls == "wizard" and h.attack_spells() and lv < (lo if h.p["ladder"] else h.wiz["min_lv"]) and not (self.slot.get(n) and self.slot[n]["drops"]):
                continue
            turns = math.ceil(dist[n] / MOVE) + 1
            if ev <= 0:
                if self.b.kind(n) == "room" and ev * turns > fb:
                    fb, fbt = ev * turns, n
                continue
            sc = ev / turns ** h.p["dist"]
            if h.p["noise"]:
                sc *= math.exp(self.rng.gauss(0, h.p["noise"]))
            if ld is not None:
                sc /= 1 + h.p["follow"] * ld.get(n, 99) / MOVE
            cands.append(n)
            if sc > best:
                best, bt = sc, n
        return bt, fbt, cands

    def teleport_level(self, n):
        if n == self.b.gh:
            return 1
        lv = self.b.level(n)
        if lv is None:  # a corridor: use the level of the nearest room or chamber
            seen, q = {n}, [n]
            for x in q:
                for y, _ in self.b.adj[x]:
                    if y not in seen:
                        if self.b.level(y):
                            return self.b.level(y)
                        seen.add(y)
                        q.append(y)
        return lv

    def teleport_opts(self, n):
        here = self.teleport_level(n)
        r = self.R["tele_range"]
        opts = [c for c in self.b.chambers if c != n and abs(self.b.level(c) - here) <= r]
        if n != self.b.gh and abs(1 - here) <= r:
            opts.append(self.b.gh)  # the Great Hall is a chamber too (Level 1)
        return opts

    def try_teleport_travel(self, h, target, dist):
        """Wizard in a chamber: teleport to a chamber within one level if that saves at least one turn of walking."""
        if h.cls != "wizard" or not h.spells.get("teleport", 0) or h.cast_this_turn:
            return False
        if self.R["tele_from"] == "chamber" and self.b.kind(h.pos) != "chamber":
            return False
        if target not in dist:
            return False
        opts = self.teleport_opts(h.pos)
        if not opts:
            return False
        pos = h.pos
        h.pos = target
        back, _ = self.dijkstra(h)  # distances from the target (costs are near-symmetric)
        h.pos = pos
        best = min(opts, key=lambda c: back.get(c, 1e18))
        walk_turns = math.ceil(dist[target] / MOVE)
        tele_turns = 1 + math.ceil(back.get(best, 1e18) / MOVE)
        if tele_turns >= walk_turns:
            return False
        if not self.R["tele_keep"]:
            h.spells["teleport"] -= 1
        h.cast_this_turn = True
        h.stats["teleports"] += 1
        self.log(f"  {h.cls}{h.idx} teleports {pos} -> {best} (toward {target})")
        h.prev, h.pos = None, best
        if not self.cleared(best):
            self.encounter(h)
        else:
            self.end_turn(h)
        return True

    # ---------- turn
    def take_turn(self, h):
        h.cast_this_turn = False
        if h.lose:
            h.lose -= 1
            return
        if h.regen:
            self.regain(h)
            return
        nofight = h.limp > 0
        if nofight:
            h.limp -= 1
        slow = h.slow > 0
        if slow:
            h.slow -= 1
        if h.resting:
            h.resting -= 1
            if self.R["rest_move"] == 0:
                if self.R["rest_fight"]:
                    self.rest_turn(h)
                else:
                    self.end_turn(h)
                return
            nofight = nofight or not self.R["rest_fight"]
            slow, rest_cap = True, self.R["rest_move"]
        else:
            rest_cap = 2
        # still in a space with a waiting monster: fight again or leave
        if not nofight and not self.cleared(h.pos) and h.pos in self.slot:
            ev, p = self.target_value(h, h.pos)
            if ev > 0 or p >= 0.4:
                self.encounter(h)
                return
        target, dist, par = self.choose_target(h)
        if target == h.pos and not self.cleared(h.pos):
            if nofight:
                self.end_turn(h)
                return
            self.encounter(h)  # best option is the monster already here: fight it
            return
        if h.has("crystal_ball") and self.try_crystal_ball(h, dist):
            return
        if not nofight and self.try_teleport_travel(h, target, dist):
            return
        path = self.path_to(par, target) if target in par else [h.pos]
        mv = self.R["move"]
        moves = MOVE if mv == "5" else d6(self.rng) + (2 if mv == "d6p2" else 0)
        if h.cls == "fighter" and self.R["f_move"]:
            moves += 1
        if slow:
            moves = min(moves, rest_cap)
        if self.R["homeward"] and h.gp >= self.goal(h) and self.has_trophy(h):
            moves = 10
        esp_used = False
        full = moves
        for nxt in path[1:]:
            kind = next((k for m, k in self.b.adj[h.pos] if m == nxt), "portal")
            if kind == "portal":
                if moves == full:  # the shortcut is a whole move
                    h.prev, h.pos = h.pos, nxt
                    h.stats["shortcuts"] += 1
                break
            if kind == "secret" and h.has("secret_door"):
                h.found.add(frozenset((h.pos, nxt)))  # you still remember these if you drop the card
            while kind == "secret" and not self.can_cross(h, h.pos, nxt, kind):
                need = 3 if h.cls == "rogue" else 5
                roll = d6(self.rng)
                h.stats["secret_tries"] += 1
                if roll >= need:
                    h.found.add(frozenset((h.pos, nxt)))
                    self.found_all.add(frozenset((h.pos, nxt)))
                    self.log(f"  {h.cls}{h.idx} finds secret door {h.pos}-{nxt}")
                    break
                self.log(f"  {h.cls}{h.idx} fails to find secret door at {h.pos}")
                if self.R["secret"] == "retry":
                    moves -= 1
                    if moves >= 1:
                        continue
                self.settle(h)
                return
            stopper = not self.cleared(nxt)
            if stopper and self.b.kind(nxt) == "room" and self.occupied(nxt, h):
                break
            if stopper and nofight:
                break  # limping: walks up to the door but doesn't go in  # entering would mean stopping in another hero's room
            if stopper:
                # ESP peek before entering an unknown room/chamber
                # (one ESP-or-Crystal-Ball use per turn; the card stays face down, only h knows it)
                if not esp_used and h.has("esp") and nxt not in self.slot:
                    esp_used = True
                    m = self.draw_monster(self.b.level(nxt))
                    self.slot[nxt] = {"monster": m, "drops": [], "known": {h.idx}}
                    h.stats["esp"] += 1
                    ev, p = self.target_value(h, nxt)
                    self.log(f"  {h.cls}{h.idx} ESP peeks {nxt}: {m['name']} (p={p:.2f})")
                    if ev <= 0:
                        self.park(nxt)
                        self.settle(h)  # chose not to enter: the turn ends
                        return
                # wizard ranged spell from outside
                can_stop_here = not (self.occupied(h.pos, h) and self.b.kind(h.pos) != "chamber")
                if h.cls == "wizard" and h.nspells() and can_stop_here and not h.cast_this_turn:
                    s = self.slot.get(nxt)
                    p, mode = self.best_mode(h, self.seen_monster(h, s), self.b.level(nxt))
                    worth = self.b.kind(nxt) == "room" or (s and s["drops"]) or p < 0.25
                    if mode in ("fireball", "lightning") and (worth or self.p_hit_melee(h, s, nxt) < 0.4):
                        self.cast(h, nxt, mode)
                        return
            h.prev, h.pos = h.pos, nxt
            moves -= 1
            if stopper:
                self.encounter(h)
                return
            if moves == 0:
                break
        self.settle(h)

    def regain(self, h):
        n = 99 if self.R["regen_amt"] == "full" else d6(self.rng)
        cap = h.maxspells() - h.nspells()
        for _ in range(min(n, cap)):
            # regain the most-depleted spell type
            s = max(h.book, key=lambda s: h.book[s] - h.spells.get(s, 0))
            h.spells[s] = h.spells.get(s, 0) + 1
        h.regen = self.R["regen_wait"] and h.maxspells() - h.nspells() > h.wiz["refill"]
        h.stats["regains"] += 1
        self.log(f"  {h.cls}{h.idx} regains spells -> {dict(h.spells)}")

    def refill_spot(self, n):
        if n == self.b.gh:
            return True
        return self.R["regen_where"] == "chamber" and self.b.kind(n) == "chamber" and self.cleared(n)

    def has_trophy(self, h):
        if not self.R["trophy"]:
            return True
        need = SAFE_LEVELS[h.cls][1]
        return any(c["level"] >= need for c in h.cards)

    def settle(self, h):
        """End of movement without an encounter: don't end on another hero's non-chamber space."""
        while self.occupied(h.pos, h) and self.b.kind(h.pos) != "chamber" and h.prev:
            h.pos, h.prev = h.prev, None
        self.end_turn(h)

    def end_turn(self, h):
        if h.pos == self.b.gh and self.R["hourglass"] in ("hall", "winhall"):
            h.hourglass = 0
        if h.pos == self.b.gh and h.gp >= self.goal(h) and self.has_trophy(h):
            h.won = True
            return
        if h.cls == "wizard" and self.refill_spot(h.pos) and h.nspells() < h.maxspells() and (
                h.attack_spells() <= max(2, h.wiz["home_at"]) or h.maxspells() - h.nspells() > h.wiz["refill"]):
            if self.R["regen_wait"]:
                h.regen = True
            else:
                self.regain(h)

    def reveal(self, h, n):
        s = self.slot.get(n)
        if s:
            s["known"] = None  # a hero has entered (or cast at) the space: the card is turned face up
            return s
        m = self.draw_monster(self.b.level(n))
        s = {"monster": m, "drops": [], "known": None}
        self.slot[n] = s
        return s

    def info_gain(self, h, n):
        """Expected value of looking at n's Monster (and Treasure, for a room) before committing to it."""
        lv = self.b.level(n)
        room = self.b.kind(n) == "room"
        deck = self.mdeck[lv] or self.mdisc[lv] or self.all_monsters[lv]
        tdeck = (self.tdeck[lv] if room else []) or [None]
        drops = sum(c["gp"] for c in self.slot[n]["drops"]) * h.p["scav"] if n in self.slot else 0
        loss_melee = self.fight_back_loss(h) * h.p["risk"]
        blind = self.target_value(h, n)[0]
        tot = 0.0
        for m in deck:
            p, mode = (1.0, h.cls) if m["trap"] else self.best_mode(h, m)
            loss = 0 if mode in ("fireball", "lightning") else loss_melee
            for t in tdeck:
                gain = drops + (t["gp"] if t else 0)
                tot += max(0.0, p * gain - (1 - p) * loss)
        return tot / (len(deck) * len(tdeck)) - max(0.0, blind)

    def try_crystal_ball(self, h, dist):
        """Spend the turn scrying an unrevealed room/chamber when what it tells us beats a turn of play."""
        if h.gp >= self.goal(h) or len(self.slot) >= NUM_SLOTS:
            return False
        bt, _, cands = self.scan_targets(h, dist, None, 1, 6)
        pool = [n for n in (cands or []) if n not in self.slot and dist.get(n, 1e18) > MOVE]
        if not pool:
            return False
        # value of a normal turn ~ the best target's expected gain per turn of travel
        rate = max((self.target_value(h, n)[0] / (math.ceil(dist[n] / MOVE) + 1) for n in cands), default=0)
        best = max(pool, key=lambda n: self.info_gain(h, n))
        if self.info_gain(h, best) <= rate:
            return False
        lv = self.b.level(best)
        s = {"monster": self.draw_monster(lv), "drops": [], "known": {h.idx}}
        if self.b.kind(best) == "room":
            t = self.draw_treasure(lv)
            if t:
                s["treasure"] = t
        self.slot[best] = s
        h.stats["crystal"] += 1
        h.goal = None
        self.log(f"  {h.cls}{h.idx} Crystal Ball on {best}: {s['monster']['name']}"
                 + (f", {s['treasure']['name']} {s['treasure']['gp']}" if s.get("treasure") else ""))
        self.end_turn(h)
        return True

    def cast(self, h, n, mode):
        s = self.reveal(h, n)
        m = s["monster"]
        h.spells[mode] -= 1
        h.cast_this_turn = True
        h.stats["casts"] += 1
        if m["trap"]:
            # spell at a trap: treat as springing it on entry
            h.prev, h.pos = h.pos, n
            self.spring_trap(h, n, s)
            return
        roll = two_d6(self.rng) - self.use_wound(h, self.b.level(n))
        t = m["tgt"][mode]
        self.log(f"  {h.cls}{h.idx} casts {mode} at {m['name']} in {n}: {roll} vs {t}")
        if t is not None and roll >= t:
            h.prev, h.pos = h.pos, n
            self.win_fight(h, n, s)
        else:
            h.stats["spell_miss"] += 1
            if self.R["miss_keep"]:
                h.spells[mode] += 1
            self.park(n)
            self.end_turn(h)  # monster stays (already in slot); hero stays outside

    def encounter(self, h):
        n = h.pos
        s = self.reveal(h, n)
        m = s["monster"]
        if m["trap"]:
            self.spring_trap(h, n, s)
            return
        # wizard teleport away from a bad chamber fight
        if h.cls == "wizard" and self.b.kind(n) == "chamber" and h.spells.get("teleport", 0) and not h.cast_this_turn:
            p, _ = self.best_mode(h, m)
            if p < 0.3:
                opts = self.teleport_opts(n)
                if opts:
                    if not self.R["tele_keep"]:
                        h.spells["teleport"] -= 1
                    h.cast_this_turn = True
                    h.stats["teleports"] += 1
                    dest = self.rng.choice([c for c in opts if self.cleared(c)] or opts)
                    self.log(f"  {h.cls}{h.idx} teleports {n} -> {dest}")
                    h.prev, h.pos = None, dest
                    if not self.cleared(dest):
                        self.encounter(h)
                    else:
                        self.end_turn(h)
                    return
        if self.R["flee"] and h.prev and not (self.occupied(h.prev, h) and self.b.kind(h.prev) != "chamber") \
                and self.target_value(h, n)[0] < 0:
            h.hourglass += 1
            h.stats["fled"] += 1
            self.log(f"  {h.cls}{h.idx} flees {m['name']} in {n}")
            h.pos, h.prev = h.prev, None
            self.park(n, h)
            self.end_turn(h)
            return
        p, mode = self.best_mode(h, m, spells=(h.cls == "wizard"))
        if mode in ("fireball", "lightning"):
            # inside the space: casting still allowed, but a miss means it fights back
            h.spells[mode] -= 1
            h.cast_this_turn = True
            t = m["tgt"][mode]
        else:
            mode = h.cls
            t = m["tgt"][mode]
            if t is None and h.sword_bonus:
                t = 13
        wound = self.use_wound(h, self.b.level(n))
        roll = two_d6(self.rng) + (h.sword_bonus if mode == h.cls else 0) - wound
        if mode == "fighter" and self.R["f_reroll"] and t is not None and roll < t:
            roll = two_d6(self.rng) + h.sword_bonus - wound  # one re-roll of a missed attack
        self.log(f"  {h.cls}{h.idx} fights {m['name']} (L{m['level']}) in {n} with {mode}: {roll} vs {t}")
        h.stats["fights"] += 1
        shaken, h.shaken = h.shaken, 0  # a Shaken token lasts one fight
        if t is not None and roll >= t:
            self.win_fight(h, n, s)
        else:
            self.fight_back(h, n, s, shaken)

    def level_clear(self, h, n):
        """clear_perk: the Defeated token on a level's last room earns a Treasure card from one level down."""
        if self.R["clear_perk"] == "none" or self.b.kind(n) != "room":
            return
        lv = self.b.level(n)
        if any(not self.cleared(r) for r in self.b.rooms if self.b.level(r) == lv):
            return
        h.stats["level_clears"] += 1
        if self.R["clear_perk"] == "tokens":
            h.hourglass = 0
            return
        if self.R["clear_perk"] == "shallow" and lv >= SAFE_LEVELS[h.cls][0]:
            return
        t = self.draw_treasure(lv + 1) if lv < 6 else None
        if t:
            self.gain(h, t)
            self.log(f"    {h.cls}{h.idx} clears level {lv}: bonus {t['name']} {t['gp']}")

    def win_fight(self, h, n, s):
        del self.slot[n]
        self.mdisc[s["monster"]["level"]].append(s["monster"])
        self.defeated[n] += 1
        self.level_clear(h, n)
        shallow = self.b.kind(n) == "room" and self.b.level(n) < SAFE_LEVELS[h.cls][0]
        if self.R["hourglass"] in ("win", "winhall"):
            h.hourglass = 0
        elif self.R["hourglass"] == "win1":
            h.hourglass = max(0, h.hourglass - 1)
        if shallow and self.R["shallow"] == "token":
            h.hourglass += 1
        h.stats["wins"] += 1
        gained = list(s["drops"])
        if shallow and self.R["shallow"] != "none":
            h.stats["shallow_wins"] += 1
        if self.b.kind(n) == "room" and not (shallow and self.R["shallow"] == "notreasure"):
            t = s.get("treasure") or self.room_draw(self.b.level(n))
            if t:
                gained.append(t)
        if self.R["chamber_perk"] and self.b.kind(n) == "chamber" and self.cleared(n):
            t = self.draw_treasure(self.b.level(n))
            if t:
                gained.append(t)
        for _ in range(s.get("bounty", 0)):
            t = self.draw_treasure(self.b.level(n))
            if t:
                gained.append(t)
        for c in gained:
            self.gain(h, c)
        if gained:
            self.log(f"    loot: {', '.join(c['name'] + ' ' + str(c['gp']) for c in gained)} -> {h.gp} gp")
        self.end_turn(h)

    def spring_trap(self, h, n, s):
        m = s["monster"]
        del self.slot[n]
        self.mdisc[m["level"]].append(m)
        self.defeated[n] += 1
        h.stats["traps"] += 1
        self.level_clear(h, n)
        for c in s["drops"]:
            self.gain(h, c)
        if self.b.kind(n) == "room":
            t = s.get("treasure") or self.draw_treasure(self.b.level(n))
            if t:
                self.gain(h, t)
        if m["trap"] == "cage":
            k = 1 if d6(self.rng) <= 3 else 2
            self.log(f"  {h.cls}{h.idx} caged in {n}: {k} x {self.R['lose']}")
            self.penalize(h, k, None, n)
            self.end_turn(h)
        elif m["trap"].startswith("slide"):
            lv = int(m["trap"].split(":")[1])
            opts = [c for c in self.b.chambers if self.b.level(c) == lv]
            # prefer a cleared chamber, else random
            clear = [c for c in opts if self.cleared(c)]
            dest = self.rng.choice(clear or opts)
            self.log(f"  {h.cls}{h.idx} slides {n} -> {dest}")
            h.prev, h.pos = None, dest
            if not self.cleared(dest):
                self.encounter(h)
            else:
                self.end_turn(h)

    def room_draw(self, lv):
        """A room's Treasure: under deep_pick, draw 2 from a deep level, keep the better, the other to the bottom."""
        t = self.draw_treasure(lv)
        if t and self.R["deep_pick"] and lv >= self.R["deep_pick"] and self.tdeck[lv]:
            u = self.draw_treasure(lv)
            t, u = (t, u) if t["gp"] >= u["gp"] else (u, t)
            self.tdeck[lv].insert(0, u)
        return t

    def gain(self, h, c):
        h.cards.append(c)
        if c["effect"] == "sword" and h.cls != "wizard" and h.sword_card is None and (
                self.R["swords"] == "all" or h.cls == "fighter"):
            r = two_d6(self.rng)
            h.sword_bonus = next(b for lo, hi, b in c["sword"] if lo <= r <= hi)
            h.sword_card = c
            self.log(f"    {h.cls}{h.idx} wields {c['name']} +{h.sword_bonus}")

    def pick_drops(self, h, k):
        """Which k of h's cards a drop takes, under drop_pick. h.cards stays in the order collected."""
        row = list(h.cards)
        k = min(k, len(row))
        how = self.R["drop_pick"]
        if k == len(row):
            return row
        if how == "random":
            return self.rng.sample(row, k)
        if how == "newest":
            return row[len(row) - k:]
        if how == "choice":
            return self.choice_order(h)[:k]
        out = []
        for _ in range(k):
            if how == "die":
                c = row[(d6(self.rng) - 1) % len(row)]
            else:
                lv = (max if how == "left" else min)(x["level"] for x in row)
                c = self.rng.choice([x for x in row if x["level"] == lv])  # same-level backs look alike
            row.remove(c)
            out.append(c)
        return out

    def choice_order(self, h):
        """drop_pick=choice: the order a player gives up cards in. Useful cards last, then cheapest first."""
        def useful(c):
            return c is h.sword_card or c["effect"] in ("esp", "crystal_ball", "secret_door")
        return sorted(h.cards, key=lambda c: (useful(c), c["gp"]))

    def drop(self, h, k, s):
        """Drop k cards (chosen by drop_pick) into slot s; s=None puts them under their level's treasure pile."""
        dropped = self.pick_drops(h, k)
        ids = {id(c) for c in dropped}
        h.cards = [c for c in h.cards if id(c) not in ids]
        if s is None:
            for c in dropped:
                self.tdeck[c["level"]].insert(0, c)
        else:
            s["drops"].extend(dropped)
        if any(c is h.sword_card for c in dropped):
            spare = next((c for c in h.cards if c["effect"] == "sword"), None)
            h.sword_card = spare
            if not spare:
                h.sword_bonus = 0
        return dropped

    def fight_back(self, h, n, s, shaken=0):
        r = min(12, two_d6(self.rng) + shaken)
        if h.cls == "fighter" and self.R["f_armor"] and 6 <= r <= 7:
            r = 5  # armor: Stunned counts as a Miss
        h.stats["hit_back"] += 1
        if r == 12:
            if self.R["crush"] == "half":
                d = self.drop(h, math.ceil(len(h.cards) / 2), s)  # your choice, under drop_pick
            else:
                d = self.drop(h, len(h.cards), s)
            self.log(f"    CRUSHED (drops {len(d)})")
            h.stats["crushed"] += 1
            stats = h.stats
            if h.cls == "wizard":
                self.new_wizard_book(h)
            kept = h.cards
            h.reset()
            h.stats = stats
            h.pos = self.b.gh
            for c in kept:
                self.gain(h, c)
        elif r == 11:
            d = self.drop(h, math.ceil(len(h.cards) / 2), s)
            self.log(f"    seriously hurt (drops {len(d)})")
            h.stats["serious"] += 1
            if self.R["serious"] == "tokens":
                h.hourglass += 2
                if h.prev and not (self.occupied(h.prev, h) and self.b.kind(h.prev) != "chamber"):
                    h.pos, h.prev = h.prev, None
            else:
                h.pos, h.prev = self.b.gh, None
        elif r >= 8:
            self.drop(h, 1, s)
            self.log("    hurt")
            h.stats["hurt"] += 1
            if h.prev and not (self.occupied(h.prev, h) and self.b.kind(h.prev) != "chamber"):
                h.pos, h.prev = h.prev, None
            if not (h.cls == "fighter" and self.R["f_tough"]):
                self.penalize(h, 1, s, n)
        elif r >= 6:
            if self.R["stun"] == "token":
                h.hourglass += 1
            else:
                self.drop(h, 1, s)
            self.log("    stunned")
            h.stats["stunned"] += 1
        else:
            self.log("    missed")
        self.park(n, h)
        self.end_turn(h)

    # ---------- lose-a-turn replacements
    def is_underdog(self, h):
        if not self.R["underdog"]:
            return False
        share = lambda o: o.gp / self.goal(o)
        return share(h) <= min(share(o) for o in self.heroes)

    def atk_minus(self, h, lv=None):
        """What comes off h's attack rolls right now (negative = a bonus); lv = the level fought at, if known."""
        dare = self.R["daring"] and lv is not None and lv > SAFE_LEVELS[h.cls][1]
        return h.wound + h.hourglass - (1 if self.is_underdog(h) else 0) - (1 if dare else 0)

    def use_wound(self, h, lv=None):
        """What comes off this attack roll: Wound tokens (used up), Hourglass tokens, Underdog and Daring bonuses."""
        w = self.atk_minus(h, lv)
        h.wound = 0
        if self.R["hourglass"] == "next":
            h.hourglass = 0
        return w

    def penalize(self, h, k, s, n):
        """k lost turns (Hurt: 1, Cage Trap: 1-2), or what the 'lose' rule puts in their place.
        s: the slot of the monster that hurt h (None for a trap, whose space is now clear)."""
        how = self.R["lose"]
        h.stats["penalty"] += k
        if how == "turn":
            h.lose += k
        elif how == "wound":
            h.wound += k
        elif how == "limp":
            h.limp += k
        elif how == "slow":
            h.slow += k
        elif how == "extra":
            if h.cards:
                self.drop(h, k, s)
        elif how == "knock":
            self.knock_back(h, 5 * k)
        elif how == "hourglass":
            h.hourglass += k
        elif how == "rest":
            h.resting += k
        elif how == "shaken":
            h.shaken += k
        elif how == "bless":
            for o in self.heroes:
                if o is not h:
                    o.wound -= k  # a negative wound is a bonus on the next attack roll
        elif how == "bounty":
            if s is not None:  # a Cage Trap leaves no monster to put a bounty on
                s["bounty"] = s.get("bounty", 0) + k
        elif how == "rush":
            for _ in range(k):
                for o in self.heroes:
                    if o is not h:
                        self.free_move(o, 2)
        else:
            raise ValueError(how)

    def rest_turn(self, h):
        """lose=rest with rest_move=0 and rest_fight: fight the monster in this space, or cast next door, or stay."""
        if not self.cleared(h.pos) and h.pos in self.slot:
            ev, p = self.target_value(h, h.pos)
            if ev > 0 or p >= 0.4:
                self.encounter(h)
                return
        if h.cls == "wizard" and h.nspells() and not (self.occupied(h.pos, h) and self.b.kind(h.pos) != "chamber"):
            best = None
            for m, kind in self.b.adj[h.pos]:
                if self.cleared(m) or not self.can_cross(h, h.pos, m, kind):
                    continue
                if self.b.kind(m) == "room" and self.occupied(m, h):
                    continue
                ev, p = self.target_value(h, m)
                _, mode = self.best_mode(h, self.seen_monster(h, self.slot.get(m)), self.b.level(m))
                if mode in ("fireball", "lightning") and ev > 0 and (best is None or ev > best[0]):
                    best = (ev, m, mode)
            if best:
                self.cast(h, best[1], best[2])
                return
        self.end_turn(h)

    def walk(self, h, path, steps):
        """Move h up to `steps` spaces along path (path[0] = h.pos) through cleared spaces only,
        never ending in another hero's room or hallway space."""
        stops = [h.pos]
        for a, b in zip(path, path[1:steps + 1]):
            kind = next(k for m, k in self.b.adj[a] if m == b)
            if not self.cleared(b) or not self.can_cross(h, a, b, kind):
                break
            stops.append(b)
        while len(stops) > 1 and self.occupied(stops[-1], h) and self.b.kind(stops[-1]) != "chamber":
            stops.pop()
        if stops[-1] != h.pos:
            h.pos, h.prev = stops[-1], None

    def knock_back(self, h, steps):
        dist, par = self.dijkstra(h)
        if self.b.gh in par:
            self.walk(h, self.path_to(par, self.b.gh), steps)
            self.log(f"    knocked back to {h.pos}")

    def free_move(self, o, steps):
        """lose=rush: an opponent moves up to `steps` toward their target, between turns, without fighting."""
        if o.lose or o.regen or getattr(o, "won", False):
            return
        target, dist, par = self.choose_target(o)
        if target in par and target != o.pos:
            self.walk(o, self.path_to(par, target), steps)

    # ---------- driver
    def play(self):
        order = list(range(len(self.heroes)))
        start = self.rng.randrange(len(order))
        order = order[start:] + order[:start]
        for h in self.heroes:
            h.won = False
        for rnd in range(1, self.max_rounds + 1):
            for i in order:
                h = self.heroes[i]
                self.take_turn(h)
                if h.won:
                    self.log(f"*** {h.cls}{h.idx} wins in round {rnd} with {h.gp} gp")
                    return h, rnd
        return None, self.max_rounds


# our adopted house rules (see house-rules.md); the 12-slot rule is always on
HOUSE = {"swords": "fighter", "drop_pick": "choice", "lose": "hourglass", "hourglass": "win1", "serious": "tokens"}


def parse_rules(text):
    """'k=v,k=v' -> rules dict, typed like the RULES defaults. 'house' = our adopted house rules."""
    out = {}
    for kv in filter(None, text.replace("+", ",").split(",")):
        if kv == "house":
            out.update(HOUSE)
            continue
        k, v = kv.split("=")
        assert k in RULES, k
        d = RULES[k]
        out[k] = v in ("1", "true", "True", "yes") if isinstance(d, bool) else int(v) if isinstance(d, int) else v
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", type=int, default=1000)
    ap.add_argument("--lineup", default="rogue,cleric,fighter,wizard")
    ap.add_argument("--policy", default="ev", help="strategy per player, comma-separated; see parse_policy")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--book", default="fireball=0.7,lightning=0.3,teleport=0",
                    help="wizard spellbook target shares")
    ap.add_argument("--goal", default="", help="override gold targets, e.g. wizard=20000")
    ap.add_argument("--wiz", default="", help="wizard play style, e.g. spell_lv=4,min_lv=4,home_at=0,refill=1")
    ap.add_argument("--rules", default="", help="house rules, e.g. miss_keep=1,regen_where=chamber (see RULES)")
    a = ap.parse_args()
    rules = parse_rules(a.rules)
    for kv in filter(None, a.goal.split(",")):
        k, v = kv.split("=")
        assert k in GOAL, k
        GOAL[k] = int(v)
    for kv in filter(None, a.wiz.split(",")):
        k, v = kv.split("=")
        assert k in WIZ, k
        WIZ[k] = int(v)
    lineup = a.lineup.split(",")
    pol = a.policy.split(",")
    pol = pol * len(lineup) if len(pol) == 1 else pol
    assert len(pol) == len(lineup), a.policy
    for p, c in zip(pol, lineup):
        parse_policy(p, c)  # validate
    for c in lineup:
        assert c in CLASSES, c
    book = {k: float(v) for k, v in (kv.split("=") for kv in a.book.split(","))}
    board, monsters, treasures = Board(), load_monsters(), load_treasures()
    wins = Counter()
    rounds = []
    agg = defaultdict(Counter)
    for g in range(a.games):
        game = Game(board, monsters, treasures, lineup, pol, seed=a.seed * 100003 + g,
                    verbose=a.verbose, book=book, rules=rules)
        w, r = game.play()
        wins[f"{w.cls}{w.idx}" if w else "none"] += 1
        if w:
            rounds.append(r)
        for h in game.heroes:
            agg[f"{h.cls}{h.idx}"].update(h.stats)
    n = a.games
    print(f"{n} games, lineup {lineup}, policy {a.policy}")
    for k in [f"{c}{i}" for i, c in enumerate(lineup)] + ["none"]:
        if wins[k] or k != "none":
            print(f"  {k:10s} wins {wins[k] / n:6.1%}")
    if rounds:
        rounds.sort()
        print(f"  rounds to win: mean {sum(rounds) / len(rounds):.1f}, median {rounds[len(rounds) // 2]}")
    print("  per game:", "  ".join(
        f"{k}: crushed {v['crushed'] / n:.2f} fights {v['fights'] / n:.1f}" + (f" casts {v['casts'] / n:.1f} teleports {v['teleports'] / n:.1f}" if k.startswith("wizard") else "") for k, v in agg.items()))


if __name__ == "__main__":
    main()
