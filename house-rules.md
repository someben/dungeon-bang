# House rules

Our changes to the printed 2014 rules. Nothing printed on the board or the cards changes.

In the simulator, `--rules house` turns on the Fighter rules below. The 12-slot rule is always on.

## Only Fighters use Magic Swords

Only a Fighter adds a Magic Sword's bonus to attack rolls, and only a Fighter can use a sword against a monster with a "–" (counting it as 13). Any other Hero who finds a sword keeps it as treasure: it counts toward their gold, but gives no bonus.

## A Hurt Fighter doesn't lose a turn

When a monster's fight-back roll is 8–10 (Hurt), a Fighter still drops 1 random Treasure card and moves back 1 space. They don't take a Lose a Turn token.

## Only 12 numbered slots

A monster that isn't defeated takes a numbered slot if one of the 12 is free. It doesn't matter whether it survived a fight, a missed Fireball or Lightning Bolt from the doorway, or an ESP peek. The same rule applies to every Hero.

If all 12 slots are taken, there's no room:

- **The monster is discarded** to its level's discard pile, every time.
- **Dropped treasure from that fight goes under a monster of the player's choice**: whichever monster already waiting in a slot they pick.
- **The room or chamber stays undefeated**, with no Defeated token. The next Hero to enter draws a new Monster card from that level's pile.
- **A discarded card returns only after a reshuffle**: when that level's pile runs out and the discards are shuffled back in.

In the simulator this is `Game.park` in `sim.py`.
