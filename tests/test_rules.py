"""Rule-by-rule checks of sim.py against the 2014 rulebook (rulebook.md), with loaded dice.

  python3 -m unittest discover -s tests -v
"""
import math
import random
import sys
import unittest
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import sim  # noqa: E402

BOARD, MONSTERS, TREASURES = sim.Board(), sim.load_monsters(), sim.load_treasures()
BOOK = {"fireball": 0.7, "lightning": 0.3, "teleport": 0.0}


class Dice(random.Random):
    """random.Random whose randint() returns queued values first (each 2d6 roll takes two)."""

    def __init__(self, seed=0):
        super().__init__(seed)
        self.q = []

    def load(self, *vals):
        self.q.extend(vals)

    def randint(self, a, b):
        if self.q:
            v = self.q.pop(0)
            assert a <= v <= b, (v, a, b)
            return v
        return super().randint(a, b)


def monster(name):
    return dict(next(m for m in MONSTERS if m["name"] == name))


def treasure(name, level=None):
    return dict(next(t for t in TREASURES if t["name"] == name and (level is None or t["level"] == level)))


def new_game(lineup=("rogue", "cleric", "fighter", "wizard"), rules=None, seed=0, book=BOOK):
    g = sim.Game(BOARD, MONSTERS, TREASURES, list(lineup), "ev", seed=seed, book=book, rules=rules)
    g.rng = Dice(seed)
    for h in g.heroes:
        h.won = False
    return g


def door_room(level):
    """(room, hallway outside its door) for a room of this level."""
    for r in BOARD.rooms:
        if BOARD.level(r) == level:
            for m, k in BOARD.adj[r]:
                if k == "door" and BOARD.kind(m) == "hall":
                    return r, m
    raise LookupError(level)


def chamber(level):
    for c in BOARD.chambers:
        if BOARD.level(c) == level:
            hall = next(m for m, k in BOARD.adj[c] if BOARD.kind(m) == "hall" and k != "secret")
            return c, hall
    raise LookupError(level)


def park_others(g, keep):
    """Move every other hero far away (to distinct hallway spaces) so they don't block anything."""
    halls = [n for n in BOARD.nodes if BOARD.kind(n) == "hall"]
    for i, h in enumerate(g.heroes):
        if h is not keep:
            h.pos = halls[-1 - i]


def put_on_top(g, card):
    g.mdeck[card["level"]].append(card)


class Setup(unittest.TestCase):
    def test_decks_match_box(self):
        self.assertEqual(len(MONSTERS), 61)
        self.assertEqual(len(TREASURES), 80)
        self.assertEqual(Counter(m["level"] for m in MONSTERS), {1: 7, 2: 8, 3: 11, 4: 12, 5: 16, 6: 7})

    def test_spellbooks_d6_plus_6_from_9_9_6(self):
        # "Roll 1 die and add 6... If there are two Wizards, take turns, selecting 1 Spell card at a time"
        for seed in range(300):
            g = sim.Game(BOARD, MONSTERS, TREASURES, ["wizard", "wizard", "rogue", "cleric"], "ev", seed=seed,
                         book={"fireball": 0.5, "lightning": 0.3, "teleport": 0.2})
            tot = Counter()
            for h in g.heroes[:2]:
                self.assertTrue(7 <= h.maxspells() <= 12)
                tot.update(h.book)
            self.assertLessEqual(tot["fireball"], 9)
            self.assertLessEqual(tot["lightning"], 9)
            self.assertLessEqual(tot["teleport"], 6)
            for h in g.heroes[2:]:
                self.assertEqual(h.maxspells(), 0)

    def test_everyone_starts_in_great_hall_which_never_has_monsters(self):
        g = new_game()
        self.assertTrue(all(h.pos == BOARD.gh for h in g.heroes))
        self.assertTrue(g.cleared(BOARD.gh))
        seen = []
        orig = sim.Game.reveal
        sim.Game.reveal = lambda self, h, n: (seen.append(n), orig(self, h, n))[1]
        try:
            for seed in range(100):
                sim.Game(BOARD, MONSTERS, TREASURES, list(sim.CLASSES), "ev", seed=seed, book=BOOK).play()
        finally:
            sim.Game.reveal = orig
        self.assertNotIn(BOARD.gh, seen)


class Combat(unittest.TestCase):
    def setUp(self):
        self.g = new_game()
        self.room, self.door = door_room(4)
        self.h = self.g.heroes[2]  # fighter
        park_others(self.g, self.h)

    def enter(self, card, *dice):
        put_on_top(self.g, card)
        self.h.prev, self.h.pos = self.door, self.room
        self.g.rng.load(*dice)
        self.g.encounter(self.h)

    def test_win_room_draws_level_treasure_and_drops(self):
        top = self.g.tdeck[4][-1]
        self.enter(monster("Goblin") | {"level": 4}, 6, 6)
        self.assertEqual(self.g.defeated[self.room], 1)
        self.assertIn(top, self.h.cards)
        self.assertTrue(self.g.cleared(self.room))

    def test_fight_back_table(self):
        m = monster("Hill Giant")  # Fighter needs 9: a roll of 2 misses
        cards = [treasure("Sack of Gold", 1) for _ in range(5)]
        cases = {12: ("crushed", 5), 11: ("serious", 3), 9: ("hurt", 1), 6: ("stunned", 1), 4: ("miss", 0)}
        for roll, (what, dropped) in cases.items():
            g = new_game()
            h = g.heroes[2]
            park_others(g, h)
            h.cards = list(cards)
            put_on_top(g, m)
            h.prev, h.pos = self.door, self.room
            g.rng.load(1, 1, *({12: (6, 6), 11: (5, 6), 9: (4, 5), 6: (3, 3), 4: (2, 2)}[roll]))
            g.encounter(h)
            s = g.slot[self.room]
            self.assertIs(s["monster"], m, what)           # waits in a free numbered slot
            self.assertIsNone(s["known"], what)            # face up
            self.assertEqual(len(s["drops"]), dropped, what)  # dropped under the monster
            if what in ("crushed", "serious"):
                self.assertEqual(h.pos, BOARD.gh, what)
            if what == "hurt":
                self.assertEqual((h.pos, h.lose), (self.door, 1))
            if what in ("stunned", "miss"):
                self.assertEqual(h.pos, self.room, what)

    def test_dash_needs_a_sword_and_counts_as_13(self):
        dash = next(m for m in MONSTERS if m["tgt"]["rogue"] is None and not m["trap"])
        g = new_game()
        h = g.heroes[0]
        park_others(g, h)
        self.assertEqual(g.p_hit(dash, "rogue", 0), 0.0)
        self.assertAlmostEqual(g.p_hit(dash, "rogue", 1), 1 / 36)   # 12 + 1 = 13
        self.assertAlmostEqual(g.p_hit(dash, "rogue", 2), 3 / 36)   # 11+ with +2

    def test_magic_sword_roll_table_and_spare(self):
        g = new_game()
        f = g.heroes[2]
        g.rng.load(5, 5)                                   # 10 on the L2 sword: 10-12 = +2
        g.gain(f, treasure("Magic Sword", 2))
        self.assertEqual(f.sword_bonus, 2)
        spare = treasure("Magic Sword", 1)
        g.gain(f, spare)                                   # only 1 sword in play: second is just treasure
        self.assertEqual(f.sword_bonus, 2)
        self.assertEqual(f.gp, 1000)
        active = f.sword_card
        f.cards = [active, spare]
        g.rng.shuffle = lambda xs: xs.sort(key=lambda c: c is not active)  # random drop hits the active sword
        g.drop(f, 1, {"drops": []})
        self.assertIs(f.sword_card, spare)                 # play the other one, same token
        self.assertEqual(f.sword_bonus, 2)
        g2 = new_game()
        g2.rng.load(3, 3)                                  # 6 on the L2 sword: +1
        g2.gain(g2.heroes[2], treasure("Magic Sword", 2))
        self.assertEqual(g2.heroes[2].sword_bonus, 1)

    def test_wizard_cannot_wield_sword_but_it_counts(self):
        g = new_game()
        w = g.heroes[3]
        g.gain(w, treasure("Magic Sword", 6))
        self.assertEqual((w.sword_bonus, w.gp), (0, 2000))

    def test_house_rule_only_fighters_wield(self):
        g = new_game(rules={"swords": "fighter"})
        g.rng.load(6, 6, 6, 6)
        g.gain(g.heroes[0], treasure("Magic Sword", 6))
        g.gain(g.heroes[2], treasure("Magic Sword", 6))
        self.assertEqual((g.heroes[0].sword_bonus, g.heroes[2].sword_bonus), (0, 2))


class Chambers(unittest.TestCase):
    def test_three_monsters_one_at_a_time_no_treasure_draw(self):
        g = new_game()
        c, hall = chamber(4)
        h = g.heroes[2]
        park_others(g, h)
        n_t = len(g.tdeck[4])
        for i in range(3):
            self.assertFalse(g.cleared(c))
            put_on_top(g, monster("Goblin") | {"level": 4})
            h.prev, h.pos = hall, c
            g.rng.load(6, 6)
            g.encounter(h)
            self.assertEqual(g.defeated[c], i + 1)
        self.assertTrue(g.cleared(c))
        self.assertEqual(len(g.tdeck[4]), n_t)             # chambers never draw treasure
        self.assertEqual(h.cards, [])

    def test_chamber_win_collects_dropped_treasure(self):
        g = new_game()
        c, hall = chamber(4)
        h = g.heroes[2]
        park_others(g, h)
        loot = treasure("Huge Sapphire") if any(t["name"] == "Huge Sapphire" for t in TREASURES) else TREASURES[-1]
        g.slot[c] = {"monster": monster("Goblin") | {"level": 4}, "drops": [loot], "known": None}
        h.prev, h.pos = hall, c
        g.rng.load(6, 6)
        g.encounter(h)
        self.assertEqual(h.cards, [loot])


class Traps(unittest.TestCase):
    def test_cage_trap_in_room(self):
        for d, lost in ((2, 1), (5, 2)):
            g = new_game()
            r, door = door_room(4)
            h = g.heroes[0]
            park_others(g, h)
            put_on_top(g, next(m for m in MONSTERS if m["trap"] == "cage" and m["level"] == 4))
            top = g.tdeck[4][-1]
            h.prev, h.pos = door, r
            g.rng.load(d)
            g.encounter(h)
            self.assertEqual(h.lose, lost)
            self.assertIn(top, h.cards)                    # a trap in a room still gives a treasure
            self.assertEqual(g.defeated[r], 1)

    def test_trap_in_chamber_gives_no_treasure(self):
        g = new_game()
        c, hall = chamber(4)
        h = g.heroes[0]
        park_others(g, h)
        put_on_top(g, next(m for m in MONSTERS if m["trap"] == "cage" and m["level"] == 4))
        h.prev, h.pos = hall, c
        g.rng.load(2)
        g.encounter(h)
        self.assertEqual(h.cards, [])
        self.assertEqual(g.defeated[c], 1)

    def test_slide_trap_moves_to_level_4_chamber(self):
        g = new_game()
        r, door = door_room(5)
        h = g.heroes[2]
        park_others(g, h)
        put_on_top(g, next(m for m in MONSTERS if m["trap"] and m["trap"].startswith("slide") and m["level"] == 5))
        put_on_top(g, monster("Goblin") | {"level": 4})    # what jumps out in the chamber
        h.prev, h.pos = door, r
        g.rng.load(6, 6)
        g.encounter(h)
        self.assertEqual(BOARD.kind(h.pos), "chamber")
        self.assertEqual(BOARD.level(h.pos), 4)
        self.assertEqual(g.defeated[h.pos], 1)             # 'begin Step 2 again' there


class Wizards(unittest.TestCase):
    def setUp(self):
        self.g = new_game()
        self.w = self.g.heroes[3]
        park_others(self.g, self.w)
        self.room, self.door = door_room(5)

    def test_spell_from_doorway_miss_no_fight_back(self):
        put_on_top(self.g, monster("Hill Giant") | {"level": 5})  # Fireball needs 6: a roll of 2 misses
        self.w.pos, self.w.cards = self.door, [treasure("Sack of Gold", 1)]
        fb = self.w.spells["fireball"]
        self.g.rng.load(1, 1)
        self.g.cast(self.w, self.room, "fireball")
        self.assertEqual(self.w.spells["fireball"], fb - 1)  # cast cards are discarded
        self.assertEqual(self.w.pos, self.door)              # stayed outside
        self.assertEqual(len(self.w.cards), 1)               # monster did not fight back
        self.assertEqual(self.w.stats["hit_back"], 0)
        self.assertIsNone(self.g.slot[self.room]["known"])   # it stays there in a slot, revealed

    def test_spell_hit_moves_in_and_loots(self):
        put_on_top(self.g, monster("Goblin") | {"level": 5})
        self.w.pos = self.door
        top = self.g.tdeck[5][-1]
        self.g.rng.load(6, 6)
        self.g.cast(self.w, self.room, "fireball")
        self.assertEqual(self.w.pos, self.room)
        self.assertIn(top, self.w.cards)

    def test_unrevealed_monster_spell_chosen_before_drawing(self):
        # with no visible card the choice can only use the level's odds
        p, mode = self.g.best_mode(self.w, None, 5)
        self.assertEqual(p, max(self.g.p_level[5, m, 0] for m in ("wizard", "fireball", "lightning")
                                if m == "wizard" or self.w.spells.get(m)) if p else p)

    def test_only_one_spell_per_turn(self):
        self.w.cast_this_turn = True
        self.assertEqual(self.g.modes(self.w), ["wizard"])
        self.w.spells["teleport"] = 1
        c, _ = chamber(4)
        self.w.pos = c
        self.assertFalse(self.g.try_teleport_travel(self.w, BOARD.gh, {BOARD.gh: 50}))

    def test_teleport_then_fight_uses_no_second_spell(self):
        g = new_game(book={"fireball": 0.6, "lightning": 0.2, "teleport": 0.2})
        w = g.heroes[3]
        park_others(g, w)
        self.assertGreater(w.spells.get("teleport", 0), 0)
        c, hall = chamber(4)
        # a monster nothing can hurt, so the Wizard teleports away before combat
        nasty = monster("Troll") | {"level": 4, "tgt": dict.fromkeys(monster("Troll")["tgt"])}
        for x in g.mdeck.values():
            x.append(monster("Goblin"))  # whatever waits in the destination chamber
        put_on_top(g, nasty)
        spells_before = (w.spells.get("fireball", 0), w.spells.get("lightning", 0))
        w.cast_this_turn = False
        w.prev, w.pos = hall, c
        g.rng.load(6, 6)
        g.encounter(w)
        self.assertEqual(w.stats["teleports"], 1)
        self.assertNotEqual(w.pos, c)
        self.assertEqual(w.stats["casts"], 0)
        self.assertEqual((w.spells.get("fireball", 0), w.spells.get("lightning", 0)), spells_before)

    def test_teleport_range_and_great_hall(self):
        c4, _ = chamber(4)
        for d in self.g.teleport_opts(c4):
            self.assertLessEqual(abs(self.g.teleport_level(d) - 4), 1)
        self.assertNotIn(BOARD.gh, self.g.teleport_opts(c4))
        c2, _ = chamber(2)
        self.assertIn(BOARD.gh, self.g.teleport_opts(c2))

    def test_regaining_spells(self):
        w = self.w
        w.spells = {"fireball": 1, "lightning": 0, "teleport": 0}
        start = w.maxspells()
        w.pos = BOARD.gh
        self.g.end_turn(w)                                   # end the turn in the Great Hall
        self.assertTrue(w.regen)
        self.g.rng.load(3)
        self.g.take_turn(w)                                  # next turn: roll 1 die, take that many, turn ends
        self.assertEqual(w.nspells(), 1 + min(3, start - 1))
        self.assertEqual(w.pos, BOARD.gh)
        w.spells = dict(w.book)
        w.spells["fireball"] -= 1
        w.regen = True
        self.g.rng.load(6)
        self.g.take_turn(w)
        self.assertEqual(w.nspells(), start)                 # never more than you started with


class Specials(unittest.TestCase):
    def test_esp_hidden_from_others_and_decline_ends_turn(self):
        g = new_game()
        h = g.heroes[0]  # rogue
        park_others(g, h)
        r, door = door_room(6)
        h.cards = [treasure("ESP Medallion", 3)]
        h.pos = door
        dragon = next(m for m in MONSTERS if m["level"] == 6 and m["tgt"]["rogue"] is None and not m["trap"])
        put_on_top(g, dragon)
        dist, par = g.dijkstra(h)
        g.choose_target = lambda hero: (r, dist, par)
        g.take_turn(h)
        self.assertEqual(h.pos, door)                        # saw it, didn't go in, turn over
        s = g.slot[r]
        self.assertEqual(s["known"], {h.idx})                # face down: only the peeker knows
        self.assertIs(g.seen_monster(h, s), dragon)
        self.assertIsNone(g.seen_monster(g.heroes[1], s))
        other = g.heroes[2]
        other.prev, other.pos = door, r
        g.rng.load(1, 1, 1, 1)
        g.encounter(other)                                   # next hero to enter reveals it and fights it
        self.assertEqual(other.stats["fights"], 1)
        self.assertIsNone(g.slot[r]["known"])

    def test_crystal_ball_scry_without_moving_and_treasure_kept(self):
        g = new_game()
        h = g.heroes[1]
        park_others(g, h)
        h.pos = BOARD.gh
        h.cards = [treasure("Crystal Ball", 4)]
        g.info_gain = lambda hero, n: 1e9                    # force a scry
        dist, _ = g.dijkstra(h)
        self.assertTrue(g.try_crystal_ball(h, dist))
        self.assertEqual(h.pos, BOARD.gh)                    # did not move
        n, s = next((k, v) for k, v in g.slot.items() if v["known"] == {h.idx})
        self.assertIsNone(g.seen_monster(g.heroes[2], s))
        if BOARD.kind(n) == "room":
            t = s["treasure"]
            self.assertNotIn(t, g.tdeck[BOARD.level(n)])
            f = g.heroes[2]
            f.pos = n
            s["monster"] = monster("Goblin") | {"level": BOARD.level(n)}
            g.rng.load(6, 6)
            g.encounter(f)
            self.assertIn(t, f.cards)                        # whoever wins gets the scried treasure

    def test_secret_doors(self):
        a, b = next((n, m) for n in BOARD.adj for m, k in BOARD.adj[n]
                    if k == "secret" and BOARD.kind(n) == "hall" and BOARD.kind(m) == "hall")
        for cls_i, roll, passes in ((2, 4, False), (2, 5, True), (0, 3, True), (0, 2, False)):
            g = new_game()
            h = g.heroes[cls_i]
            park_others(g, h)
            h.pos = a
            dist, par = g.dijkstra(h)
            g.choose_target = lambda hero: (b, {b: 1}, {b: a, a: None})
            g.rng.load(roll)
            g.take_turn(h)
            self.assertEqual(h.pos == b, passes, (h.cls, roll))
            self.assertEqual(frozenset((a, b)) in h.found, passes)
        g = new_game()
        h = g.heroes[2]
        park_others(g, h)
        h.pos = a
        h.cards = [treasure("Secret Door Card", 1)]
        g.choose_target = lambda hero: (b, {b: 1}, {b: a, a: None})
        g.take_turn(h)
        self.assertEqual(h.pos, b)                           # card: no roll
        h.cards = []
        self.assertTrue(g.can_cross(h, a, b, "secret"))      # still remembered after dropping it

    def test_cannot_stop_in_another_heros_room(self):
        g = new_game()
        h = g.heroes[2]
        park_others(g, h)
        r, door = door_room(3)
        g.heroes[0].pos = r                                  # someone else is in that room
        g.slot[r] = {"monster": monster("Goblin"), "drops": [], "known": None}
        h.pos = door
        g.choose_target = lambda hero: (r, {r: 1}, {r: door, door: None})
        g.take_turn(h)
        self.assertEqual(h.pos, door)

    def test_win_only_by_ending_turn_in_great_hall(self):
        g = new_game()
        h = g.heroes[0]
        h.cards = [treasure("Sack of Gold", 1)] * 40
        h.pos = BOARD.gh
        g.end_turn(h)
        self.assertTrue(h.won)
        g2 = new_game()
        h2 = g2.heroes[0]
        h2.cards = [treasure("Sack of Gold", 1)] * 2
        h2.pos = BOARD.gh
        g2.end_turn(h2)
        self.assertFalse(h2.won)

    def test_lose_a_turn_token(self):
        g = new_game()
        h = g.heroes[0]
        h.lose, pos = 2, h.pos
        g.take_turn(h)
        self.assertEqual((h.lose, h.pos), (1, pos))


class HouseRulings(unittest.TestCase):
    """Situations the rulebook doesn't cover, ruled by the user (2026-11-20)."""

    def fill_slots(self, g, n=sim.NUM_SLOTS):
        rooms = [r for r in BOARD.rooms if BOARD.level(r) in (1, 2, 3)][:n]
        assert len(rooms) == n
        for r in rooms:
            g.slot[r] = {"monster": monster("Goblin"), "drops": [], "known": None}

    def test_unbeaten_monster_takes_a_free_slot(self):
        g = new_game()
        h = g.heroes[2]
        park_others(g, h)
        self.fill_slots(g, sim.NUM_SLOTS - 1)       # one slot left
        r, door = door_room(4)
        put_on_top(g, monster("Hill Giant"))
        h.prev, h.pos = door, r
        g.rng.load(1, 1, 2, 2)
        g.encounter(h)
        self.assertIn(r, g.slot)
        self.assertEqual(len(g.slot), sim.NUM_SLOTS)

    def test_unbeaten_monster_discarded_when_slots_full(self):
        g = new_game()
        h = g.heroes[2]
        park_others(g, h)
        self.fill_slots(g)
        r, door = door_room(4)
        m = monster("Hill Giant")
        put_on_top(g, m)
        h.prev, h.pos = door, r
        g.rng.load(1, 1, 2, 2)                      # miss, then the monster misses too: nothing dropped
        g.encounter(h)
        self.assertNotIn(r, g.slot)
        self.assertTrue(any(x is m for x in g.mdisc[4]))
        self.assertFalse(g.cleared(r))              # still unbeaten: a new monster jumps out next time

    def test_discarded_monster_replaced_by_random_draw_from_remaining_deck(self):
        g = new_game()
        h = g.heroes[2]
        park_others(g, h)
        self.fill_slots(g)
        r, door = door_room(4)
        giant = monster("Hill Giant")
        put_on_top(g, giant)
        h.prev, h.pos = door, r
        g.rng.load(1, 1, 2, 2)                      # miss, monster misses: discarded (no drops)
        g.encounter(h)
        self.assertNotIn(r, g.slot)
        remaining = list(g.mdeck[4])
        self.assertFalse(any(x is giant for x in remaining))
        # next hero in: a new card comes off the top of the remaining Level 4 pile
        other = g.heroes[0]
        other.prev, other.pos = door, r
        g.rng.load(1, 1, 2, 2)
        g.encounter(other)
        drawn = g.mdisc[4][-1]                      # it was drawn, missed, and discarded too
        self.assertIs(drawn, remaining[-1])         # the top card of the remaining pile
        self.assertIsNot(drawn, giant)
        # the discarded card only returns once the pile runs out and the discards are reshuffled
        g.mdeck[4] = []
        self.assertTrue(any(x is giant for x in g.mdisc[4]))
        back = g.draw_monster(4)
        self.assertEqual(g.mdisc[4], [])
        self.assertTrue(any(x is giant for x in g.mdeck[4] + [back]))

    def test_full_slots_discard_and_drops_go_under_a_waiting_monster(self):
        g = new_game()
        h = g.heroes[2]
        park_others(g, h)
        gold = treasure("Sack of Gold", 1)
        h.cards = [gold]
        self.fill_slots(g)
        r, door = door_room(4)
        giant = monster("Hill Giant")
        put_on_top(g, giant)
        h.prev, h.pos = door, r
        g.rng.load(1, 1, 3, 3)                      # miss, then Stunned: drops a card
        g.encounter(h)
        self.assertNotIn(r, g.slot)                 # no room: the monster is discarded
        self.assertTrue(any(x is giant for x in g.mdisc[4]))
        self.assertEqual(len(g.slot), sim.NUM_SLOTS)
        holders = [k for k, v in g.slot.items() if gold in v["drops"]]
        self.assertEqual(len(holders), 1)           # the treasure went under one waiting monster
        self.assertEqual(h.cards, [])

    def test_spell_miss_and_esp_peek_same_rule(self):
        g = new_game()
        w = g.heroes[3]
        park_others(g, w)
        r, door = door_room(5)
        put_on_top(g, monster("Hill Giant") | {"level": 5})
        w.pos = door
        g.rng.load(1, 1)
        g.cast(w, r, "fireball")                    # missed spell, slot free: it waits
        self.assertIn(r, g.slot)
        g1 = new_game()
        w1 = g1.heroes[3]
        park_others(g1, w1)
        self.fill_slots(g1)
        put_on_top(g1, monster("Hill Giant") | {"level": 5})
        w1.pos = door
        g1.rng.load(1, 1)
        g1.cast(w1, r, "fireball")                  # missed spell, slots full: discarded, same as everyone
        self.assertNotIn(r, g1.slot)
        # an ESP peek takes a free slot too
        g2 = new_game()
        h = g2.heroes[0]
        park_others(g2, h)
        r2, door2 = door_room(6)
        h.cards, h.pos = [treasure("ESP Medallion", 3)], door2
        put_on_top(g2, next(m for m in MONSTERS if m["level"] == 6 and m["tgt"]["rogue"] is None and not m["trap"]))
        dist, par = g2.dijkstra(h)
        g2.choose_target = lambda hero: (r2, dist, par)
        g2.take_turn(h)
        self.assertEqual(g2.slot[r2]["known"], {h.idx})

    def test_hurt_fighter_does_not_lose_a_turn(self):
        for rules, lost in (({}, 1), (sim.parse_rules("house"), 0)):
            g = new_game(rules=rules)
            f = g.heroes[2]
            park_others(g, f)
            f.cards = [treasure("Sack of Gold", 1)]
            r, door = door_room(4)
            put_on_top(g, monster("Hill Giant"))
            f.prev, f.pos = door, r
            g.rng.load(1, 1, 4, 5)                  # miss, then Hurt (9)
            g.encounter(f)
            self.assertEqual((f.lose, f.pos, len(f.cards)), (lost, door, 0))

    def test_crushed_wizard_gets_new_spellbook(self):
        g = new_game(lineup=("wizard", "wizard", "rogue", "fighter"),
                     book={"fireball": 0.5, "lightning": 0.3, "teleport": 0.2})
        w, other = g.heroes[0], g.heroes[1]
        park_others(g, w)
        w.spells = {"fireball": 0, "lightning": 0, "teleport": 0}
        r, door = door_room(4)
        put_on_top(g, monster("Hill Giant"))
        w.prev, w.pos = door, r
        g.rng.load(1, 1, 6, 6, 3)                   # miss, Crushed!, new book size 3 + 6 = 9
        g.encounter(w)
        self.assertEqual(w.pos, BOARD.gh)
        self.assertEqual(w.maxspells(), 9)
        self.assertEqual(w.nspells(), 9)
        for k, cap in {"fireball": 9, "lightning": 9, "teleport": 6}.items():
            self.assertLessEqual(w.book.get(k, 0) + other.book.get(k, 0), cap)

    def test_own_drops_are_collected_too(self):
        g = new_game()
        c, hall = chamber(4)
        h = g.heroes[2]
        park_others(g, h)
        mine = treasure("Gold Cup", 3)
        g.slot[c] = {"monster": monster("Goblin") | {"level": 4}, "drops": [mine], "known": None}
        h.prev, h.pos = hall, c
        g.rng.load(6, 6)
        g.encounter(h)
        self.assertIn(mine, h.cards)


if __name__ == "__main__":
    unittest.main()
