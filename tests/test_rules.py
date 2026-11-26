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
        g.rng.sample = lambda xs, k: [active]             # random drop hits the active sword
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
        for rules, lost in (({}, 1), ({"f_tough": True}, 0)):
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


class Replacements(unittest.TestCase):
    """Candidate replacements for random drops (drop_pick) and Lose a Turn (lose)."""

    def setUp(self):
        self.room, self.door = door_room(4)

    def hand(self):
        return [treasure("Sack of Gold", 2), treasure("Silver Coffer", 6), treasure("Sack of Gold", 1),
                treasure("Silver Ring", 5)]            # collected in this order

    def hit_back(self, rules, roll, cls=0, cards=None):
        """Hero `cls` misses the Hill Giant, then it rolls `roll` (as two dice)."""
        g = new_game(rules=sim.parse_rules(rules))
        h = g.heroes[cls]
        park_others(g, h)
        h.cards = cards if cards is not None else self.hand()
        put_on_top(g, monster("Hill Giant"))
        h.prev, h.pos = self.door, self.room
        g.rng.load(1, 1, *roll)
        return g, h

    def dropped(self, g):
        return [c["name"] for c in g.slot[self.room]["drops"]]

    def test_drop_pick(self):
        cases = {"newest": ["Silver Ring"], "lowest": ["Sack of Gold"], "left": ["Silver Coffer"]}
        for how, want in cases.items():
            g, h = self.hit_back(f"drop_pick={how}", (3, 3))     # Stunned: drop 1
            g.encounter(h)
            self.assertEqual(self.dropped(g), want, how)
        for die, want in ((2, "Silver Coffer"), (6, "Silver Coffer"), (5, "Sack of Gold")):
            g, h = self.hit_back("drop_pick=die", (3, 3, die))   # count along the row, wrapping: 6 -> card 2
            g.encounter(h)
            self.assertEqual(self.dropped(g), [want], die)
        g, h = self.hit_back("drop_pick=lowest", (5, 6))         # Seriously Hurt: the 2 lowest levels
        g.encounter(h)
        self.assertEqual(sorted(self.dropped(g)), ["Sack of Gold", "Sack of Gold"])
        self.assertEqual([c["level"] for c in h.cards], [6, 5])   # the rest stay in the order collected

    def test_drop_of_your_choice(self):
        esp = next(t for t in TREASURES if t["effect"] == "esp")
        cards = self.hand() + [dict(esp)]
        g, h = self.hit_back("drop_pick=choice", (3, 3), cards=list(cards))   # Stunned: the cheapest
        g.encounter(h)
        self.assertEqual([c["gp"] for c in g.slot[self.room]["drops"]], [250])
        g, h = self.hit_back("drop_pick=choice", (5, 6), cards=list(cards))   # Seriously Hurt: 3 of 5
        g.encounter(h)
        self.assertEqual(sorted(c["gp"] for c in g.slot[self.room]["drops"]), [250, 500, 2000])
        self.assertTrue(h.has("esp"))                    # useful cards go last, whatever they're worth
        self.assertEqual([c["name"] for c in h.cards if not c["effect"]], ["Silver Coffer"])

    def test_lose_turn_is_printed_default(self):
        g, h = self.hit_back("", (4, 5))
        g.encounter(h)
        self.assertEqual((h.lose, h.pos, len(h.cards)), (1, self.door, 3))

    def test_wound(self):
        g, h = self.hit_back("lose=wound", (4, 5))
        g.encounter(h)
        self.assertEqual((h.lose, h.wound, h.pos), (0, 1, self.door))
        put_on_top(g, monster("Goblin"))                          # Rogue needs 3
        g.slot.clear()
        r, door = door_room(1)
        h.prev, h.pos = door, r
        g.rng.load(1, 2, 1, 1)                                    # 3 - 1 = 2: miss, then it misses back
        g.encounter(h)
        self.assertIn(r, g.slot)
        self.assertEqual(h.wound, 0)                              # used up by that one roll

    def test_extra_drop(self):
        g, h = self.hit_back("lose=extra", (4, 5))
        g.encounter(h)
        self.assertEqual((h.lose, len(g.slot[self.room]["drops"]), len(h.cards)), (0, 2, 2))

    def test_limp_moves_but_does_not_fight(self):
        g, h = self.hit_back("lose=limp", (4, 5))
        g.encounter(h)
        self.assertEqual((h.lose, h.limp), (0, 1))
        fights = h.stats["fights"]
        for _ in range(3):
            g.take_turn(h)
            if h.limp == 0:
                break
        self.assertEqual(h.stats["fights"], fights)
        self.assertTrue(g.cleared(h.pos))

    def test_slow_moves_only_two(self):
        g, h = self.hit_back("lose=slow", (4, 5))
        g.encounter(h)
        self.assertEqual((h.lose, h.slow), (0, 1))
        start = h.pos
        g.take_turn(h)
        steps = {start: 0}
        q = [start]
        for x in q:
            for y, _ in BOARD.adj[x]:
                if y not in steps:
                    steps[y] = steps[x] + 1
                    q.append(y)
        self.assertLessEqual(steps[h.pos], 2)
        self.assertEqual(h.slow, 0)

    def test_knock_back_toward_great_hall(self):
        g, h = self.hit_back("lose=knock", (4, 5))
        before = g.dijkstra(type("P", (), {"pos": self.door, "cls": "rogue", "found": set(),
                                           "has": lambda self, e: False})())[0][BOARD.gh]
        g.encounter(h)
        self.assertEqual(h.lose, 0)
        self.assertNotEqual(h.pos, self.door)
        self.assertLess(g.dijkstra(h)[0][BOARD.gh], before)

    def test_rush_moves_everyone_else(self):
        g, h = self.hit_back("lose=rush", (4, 5))
        others = [o for o in g.heroes if o is not h]
        for o in others:
            o.pos = BOARD.gh
        g.encounter(h)
        self.assertEqual(h.lose, 0)
        self.assertTrue(any(o.pos != BOARD.gh for o in others))

    def test_cage_gives_two_penalties_on_a_high_roll(self):
        g = new_game(rules={"lose": "wound"})
        r, door = door_room(4)
        h = g.heroes[0]
        park_others(g, h)
        put_on_top(g, next(m for m in MONSTERS if m["trap"] == "cage" and m["level"] == 4))
        h.prev, h.pos = door, r
        g.rng.load(5)
        g.encounter(h)
        self.assertEqual((h.lose, h.wound), (0, 2))

    def test_resting_stays_put(self):
        g, h = self.hit_back("lose=rest+rest_move=0+rest_fight=1", (4, 5))
        g.encounter(h)
        self.assertEqual((h.lose, h.resting, h.pos), (0, 1, self.door))
        g.take_turn(h)
        self.assertEqual((h.resting, h.pos), (0, self.door))

    def test_resting_fights_the_monster_in_its_space(self):
        g, h = self.hit_back("lose=rest+rest_move=0+rest_fight=1", (4, 5))
        g.encounter(h)
        h.pos = self.room                                         # say it couldn't step back
        g.slot[self.room]["monster"] = monster("Goblin")
        g.rng.load(6, 6)
        g.take_turn(h)
        self.assertTrue(g.cleared(self.room))

    def test_resting_wizard_casts_next_door(self):
        g = new_game(rules={"lose": "rest", "rest_move": 0, "rest_fight": True})
        w = g.heroes[3]
        park_others(g, w)
        w.spells = {"fireball": 3, "lightning": 0, "teleport": 0}
        w.resting, w.pos = 1, self.door
        g.slot[self.room] = {"monster": monster("Hill Giant"), "drops": [], "known": None}
        g.rng.load(6, 6)
        g.take_turn(w)
        self.assertEqual((w.stats["casts"], w.pos), (1, self.room))
        self.assertTrue(g.cleared(self.room))

    def test_resting_moves_two_and_does_not_fight(self):
        g, h = self.hit_back("lose=rest", (4, 5))               # defaults: rest_move=2, rest_fight off
        g.encounter(h)
        self.assertEqual((h.lose, h.resting), (0, 1))
        start, fights = h.pos, h.stats["fights"]
        g.take_turn(h)
        steps = {start: 0}
        q = [start]
        for x in q:
            for y, _ in BOARD.adj[x]:
                if y not in steps:
                    steps[y] = steps[x] + 1
                    q.append(y)
        self.assertLessEqual(steps[h.pos], 2)
        self.assertEqual((h.resting, h.stats["fights"]), (0, fights))
        self.assertTrue(g.cleared(h.pos))

    def test_resting_in_place_without_fighting(self):
        g, h = self.hit_back("lose=rest+rest_move=0", (4, 5))
        g.encounter(h)
        h.pos = self.room                                         # say it couldn't step back
        g.take_turn(h)
        self.assertEqual((h.pos, h.stats["fights"]), (self.room, 1))
        self.assertIn(self.room, g.slot)

    def goblin_fight(self, g, h, dice):
        """h fights a Goblin in a level-1 room (Rogue needs 3); returns whether it won."""
        r, door = door_room(1)
        g.slot.pop(r, None)
        g.defeated[r] = 0
        put_on_top(g, monster("Goblin"))
        h.prev, h.pos = door, r
        g.rng.load(*dice)
        g.encounter(h)
        return g.cleared(r)

    def test_hourglass_tokens(self):
        g, h = self.hit_back("lose=hourglass", (4, 5))
        g.encounter(h)
        self.assertEqual((h.lose, h.hourglass), (0, 1))

    def test_hourglass_clearing(self):
        # (rule, after a missed attack, after a won fight, after ending a turn in the Great Hall)
        for rule, miss, win, hall in (("next", 0, 0, 0), ("win", 2, 0, 0), ("hall", 2, 2, 0), ("game", 2, 2, 2)):
            g = new_game(rules={"lose": "hourglass", "hourglass": rule})
            h = g.heroes[0]
            park_others(g, h)
            h.hourglass = 2
            self.assertFalse(self.goblin_fight(g, h, (2, 2, 1, 1)), rule)   # 4 - 2 = 2 misses; it misses back
            self.assertEqual(h.hourglass, miss, rule)
            h.hourglass = max(h.hourglass, 0)
            won = self.goblin_fight(g, h, (2, 3))                           # 5 - tokens >= 3
            self.assertTrue(won, rule)
            self.assertEqual(h.hourglass, win, rule)
            h.pos = BOARD.gh
            g.end_turn(h)
            self.assertEqual(h.hourglass, hall, rule)

    def test_hourglass_cage_gives_two(self):
        g = new_game(rules={"lose": "hourglass"})
        r, door = door_room(4)
        h = g.heroes[0]
        park_others(g, h)
        put_on_top(g, next(m for m in MONSTERS if m["trap"] == "cage" and m["level"] == 4))
        h.prev, h.pos = door, r
        g.rng.load(5)
        g.encounter(h)
        self.assertEqual((h.lose, h.hourglass), (0, 2))

    def test_shaken_raises_the_next_fight_back(self):
        g, h = self.hit_back("lose=shaken", (4, 5))
        g.encounter(h)
        self.assertEqual((h.lose, h.shaken), (0, 1))
        h.cards = [treasure("Sack of Gold", 1)] * 3
        h.prev, h.pos = self.door, self.room
        g.rng.load(1, 1, 5, 6)                                    # miss, then 11 + 1 = Crushed
        g.encounter(h)
        self.assertEqual((h.stats["crushed"], h.pos, h.cards, h.shaken), (1, BOARD.gh, [], 0))

    def test_bless_gives_everyone_else_plus_one(self):
        g, h = self.hit_back("lose=bless", (4, 5))
        g.encounter(h)
        self.assertEqual(h.lose, 0)
        self.assertEqual([o.wound for o in g.heroes], [0, -1, -1, -1])
        c = g.heroes[1]                                           # Cleric needs 4 against a Goblin
        r, door = door_room(1)
        put_on_top(g, monster("Goblin"))
        c.prev, c.pos = door, r
        g.rng.load(1, 2)                                          # 3 + 1 = 4: a hit
        g.encounter(c)
        self.assertTrue(g.cleared(r))
        self.assertEqual(c.wound, 0)

    def test_bounty_pays_whoever_beats_the_monster(self):
        g, h = self.hit_back("lose=bounty", (4, 5))
        g.encounter(h)
        self.assertEqual((h.lose, g.slot[self.room]["bounty"]), (0, 1))
        o = g.heroes[1]
        o.cards = []
        o.prev, o.pos = self.door, self.room
        g.rng.load(6, 6)
        g.encounter(o)
        self.assertEqual(len(o.cards), 3)                         # the drop, the room's Treasure, the bounty
        self.assertTrue(all(c["level"] == 4 for c in o.cards[1:]))

    def test_bounty_on_a_cage_trap_does_nothing(self):
        g = new_game(rules={"lose": "bounty"})
        r, door = door_room(4)
        h = g.heroes[0]
        park_others(g, h)
        put_on_top(g, next(m for m in MONSTERS if m["trap"] == "cage" and m["level"] == 4))
        h.prev, h.pos = door, r
        g.rng.load(5)
        g.encounter(h)
        self.assertEqual(h.lose, 0)
        self.assertTrue(g.cleared(r))

    def test_tough_fighter_skips_any_replacement(self):
        for how in ("wound", "extra", "limp", "slow"):
            g, h = self.hit_back(f"f_tough=1+lose={how}", (4, 5), cls=2)
            g.encounter(h)
            self.assertEqual((h.lose, h.wound, h.limp, h.slow, len(h.cards)), (0, 0, 0, 0, 3), how)



class LevelClearPerk(unittest.TestCase):
    def setup(self, rules):
        g = new_game(rules=rules)
        h = g.heroes[0]
        park_others(g, h)
        rooms = [r for r in BOARD.rooms if BOARD.level(r) == 1]
        for r in rooms[1:]:
            g.defeated[r] = 1
        last = rooms[0]
        door = next(m for m, k in BOARD.adj[last] if k == "door")
        put_on_top(g, monster("Goblin"))
        h.prev, h.pos, h.cards = door, last, []
        g.rng.load(6, 6)
        return g, h

    def test_last_room_of_a_level_pays_a_deeper_treasure(self):
        g, h = self.setup({"clear_perk": "deeper"})
        top2 = g.tdeck[2][-1]
        g.encounter(h)
        self.assertEqual(len(h.cards), 2)                         # the room's Treasure and the bonus
        self.assertIn(top2, h.cards)
        self.assertEqual(h.stats["level_clears"], 1)

    def test_no_perk_by_default_or_before_the_last_room(self):
        g, h = self.setup({})
        g.encounter(h)
        self.assertEqual(len(h.cards), 1)
        g, h = self.setup({"clear_perk": "deeper"})
        g.defeated[[r for r in BOARD.rooms if BOARD.level(r) == 1][1]] = 0
        g.encounter(h)
        self.assertEqual(len(h.cards), 1)

    def test_chambers_dont_count(self):
        g = new_game(rules={"clear_perk": "deeper"})
        for r in BOARD.rooms:
            if BOARD.level(r) == 2:
                g.defeated[r] = 1
        c, hall = chamber(2)
        h = g.heroes[0]
        park_others(g, h)
        h.prev, h.pos, h.cards = hall, c, []
        g.slot[c] = {"monster": monster("Goblin") | {"level": 2}, "drops": [], "known": None}
        g.rng.load(6, 6)
        g.encounter(h)
        self.assertEqual(h.cards, [])



class Tweaks(unittest.TestCase):
    """Small rule ideas on top of the house rules."""

    def fight(self, rules, dice, cls=0, cards=None, lv=4, m="Hill Giant"):
        g = new_game(rules=rules)
        h = g.heroes[cls]
        park_others(g, h)
        h.cards = list(cards or [])
        r, door = door_room(lv)
        put_on_top(g, monster(m))
        h.prev, h.pos = door, r
        g.rng.load(*dice)
        g.encounter(h)
        return g, h, r

    def test_stunned_gives_a_token_instead_of_a_drop(self):
        g, h, r = self.fight({"stun": "token", "lose": "hourglass"}, (1, 1, 3, 3), cards=[treasure("Sack of Gold", 1)])
        self.assertEqual((len(h.cards), h.hourglass, g.slot[r]["drops"]), (1, 1, []))

    def test_crushed_drops_half(self):
        cards = [treasure("Sack of Gold", 1), treasure("Silver Coffer", 6), treasure("Sack of Gold", 2)]
        g, h, r = self.fight({"crush": "half", "drop_pick": "choice"}, (1, 1, 6, 6), cards=cards)
        self.assertEqual(h.pos, BOARD.gh)
        self.assertEqual([c["name"] for c in h.cards], ["Silver Coffer"])
        self.assertEqual(len(g.slot[r]["drops"]), 2)

    def test_chamber_perk_on_the_third_token(self):
        g = new_game(rules={"chamber_perk": True})
        c, hall = chamber(4)
        h = g.heroes[0]
        park_others(g, h)
        h.cards = []
        g.defeated[c] = 2
        g.slot[c] = {"monster": monster("Goblin") | {"level": 4}, "drops": [], "known": None}
        top = g.tdeck[4][-1]
        h.prev, h.pos = hall, c
        g.rng.load(6, 6)
        g.encounter(h)
        self.assertEqual(h.cards, [top])
        g.defeated[c] = 1                                         # not the third token: nothing
        g.slot[c] = {"monster": monster("Goblin") | {"level": 4}, "drops": [], "known": None}
        h.cards = []
        h.prev, h.pos = hall, c
        g.rng.load(6, 6)
        g.encounter(h)
        self.assertEqual(h.cards, [])

    def test_deep_pick_keeps_the_better_card(self):
        g = new_game(rules={"deep_pick": 4})
        lo, hi = treasure("Sack of Gold", 4), treasure("Silver Coffer", 6) | {"level": 4}
        g.tdeck[4] += [hi, lo]                                    # lo drawn first, then hi
        h = g.heroes[0]
        park_others(g, h)
        h.cards = []
        r, door = door_room(4)
        put_on_top(g, monster("Goblin") | {"level": 4})
        h.prev, h.pos = door, r
        g.rng.load(6, 6)
        g.encounter(h)
        self.assertEqual(h.cards, [hi])
        self.assertIs(g.tdeck[4][0], lo)                          # the other goes to the bottom

    def test_homeward_moves_ten(self):
        g = new_game(rules={"homeward": True})
        h = g.heroes[0]
        park_others(g, h)
        h.cards = [treasure("Silver Coffer", 6)] * 3              # 12,000 gp: enough for a Rogue
        dist0 = None
        for n in BOARD.nodes:                                     # a cleared hallway 10+ spaces out
            if BOARD.kind(n) == "hall":
                h.pos = n
                d = g.dijkstra(h)[0][BOARD.gh]
                if 10 <= d < 12:
                    dist0 = d
                    break
        self.assertIsNotNone(dist0)
        for r in BOARD.rooms + BOARD.chambers:
            g.defeated[r] = 3
        g.take_turn(h)
        self.assertLessEqual(g.dijkstra(h)[0][BOARD.gh], dist0 - 10)

    def test_underdog_bonus(self):
        g = new_game(rules={"underdog": True})
        for o in g.heroes:
            o.cards = [treasure("Sack of Gold", 1)]
        g.heroes[0].cards = []
        self.assertEqual([g.atk_minus(o) for o in g.heroes], [-1, 0, 0, 0])
        g2, h, r = self.fight({"underdog": True}, (1, 1), lv=1, m="Goblin")   # 2 + 1 = 3: a Rogue hits
        self.assertTrue(g2.cleared(r))


    def test_seriously_hurt_takes_two_tokens_and_steps_back(self):
        cards = [treasure("Sack of Gold", 1) for _ in range(4)]
        g, h, r = self.fight({"serious": "tokens", "lose": "hourglass"}, (1, 1, 5, 6), cards=cards)
        self.assertEqual((h.hourglass, len(h.cards), len(g.slot[r]["drops"])), (2, 2, 2))
        self.assertNotEqual(h.pos, BOARD.gh)
        self.assertEqual(BOARD.kind(h.pos), "hall")

    def test_flee_before_a_bad_fight(self):
        cards = [treasure("Silver Coffer", 6) for _ in range(3)]
        g = new_game(rules={"flee": True, "lose": "hourglass"})
        h = g.heroes[0]                                          # a Rogue needs 10 vs a Hill Giant
        park_others(g, h)
        h.cards = list(cards)
        r, door = door_room(4)
        put_on_top(g, monster("Hill Giant"))
        h.prev, h.pos = door, r
        g.encounter(h)
        self.assertEqual((h.pos, h.hourglass, len(h.cards), h.stats["fights"]), (door, 1, 3, 0))
        self.assertIn(r, g.slot)

    def test_hourglass_winhall_clears_either_way(self):
        g = new_game(rules={"lose": "hourglass", "hourglass": "winhall"})
        h = g.heroes[0]
        h.hourglass, h.pos = 2, BOARD.gh
        g.end_turn(h)
        self.assertEqual(h.hourglass, 0)

    def test_shortcut_great_hall_to_cleared_chamber(self):
        g = new_game(rules={"shortcut": True})
        h = g.heroes[2]
        park_others(g, h)
        c = max(BOARD.chambers, key=BOARD.level)
        g.defeated[c] = 3
        self.assertIn((c, "portal"), g.portals(BOARD.gh))
        self.assertEqual(g.dijkstra(h)[0][c], sim.MOVE)
        g.defeated[c] = 2
        self.assertNotIn((c, "portal"), g.portals(BOARD.gh))
        g2 = new_game()
        self.assertEqual(g2.portals(BOARD.gh), [])


    def test_shallow_rooms(self):
        # a Fighter's printed safest levels are 3-5, so a level-1 room is shallow for them
        g, h, r = self.fight({"shallow": "notreasure"}, (6, 6), cls=2, lv=1, m="Goblin")
        self.assertTrue(g.cleared(r))
        self.assertEqual(h.cards, [])
        g, h, r = self.fight({"shallow": "token", "lose": "hourglass"}, (6, 6), cls=2, lv=1, m="Goblin")
        self.assertEqual((len(h.cards), h.hourglass), (1, 1))
        g, h, r = self.fight({"shallow": "notreasure"}, (6, 6), cls=0, lv=1, m="Goblin")   # Rogue: 1-3
        self.assertEqual(len(h.cards), 1)


    def test_daring_bonus_below_your_safest_levels(self):
        g, h, r = self.fight({"daring": True}, (4, 5), cls=0, lv=4)   # Rogue (1-3) at level 4: 9 + 1 = 10 hits
        self.assertTrue(g.cleared(r))
        g, h, r = self.fight({"daring": True}, (3, 5, 1, 1), cls=2, lv=4)   # Fighter (3-5): 8 misses 9, no bonus
        self.assertFalse(g.cleared(r))

    def test_hourglass_win1_takes_one_off(self):
        g = new_game(rules={"lose": "hourglass", "hourglass": "win1"})
        h = g.heroes[0]
        park_others(g, h)
        h.hourglass = 2
        r, door = door_room(1)
        put_on_top(g, monster("Goblin"))
        h.prev, h.pos = door, r
        g.rng.load(6, 6)
        g.encounter(h)
        self.assertEqual(h.hourglass, 1)


if __name__ == "__main__":
    unittest.main()
