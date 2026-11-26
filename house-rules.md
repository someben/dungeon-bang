# House rules: the fixes that make the game work

Played as printed, the 2014 game is lopsided: Rogues and Clerics win about twice as often as Fighters and Wizards. These seven rules fix that, and they also replace the two printed mechanics that play worst: losing turns and "random" drops from a hand whose card backs show their level. Nothing printed on the board or the cards changes.

Win rates in a 4-player game with one Hero of each class, over 24,000 simulated games where every player picks a random human-like play style:

| | Rogue | Cleric | Fighter | Wizard |
|---|---|---|---|---|
| Printed rules | 31.5% | 33.6% | 15.7% | 19.2% |
| With these house rules | 25.9% | 25.4% | 23.7% | 25.0% |

When every class instead switches to the strategy that wins it the most (`python3 explore.py adapt house`, 2 rounds, 4,000 games):

| | Rogue | Cleric | Fighter | Wizard |
|---|---|---|---|---|
| Everyone on the default strategy | 24.3% | 28.6% | 24.3% | 22.7% |
| After 2 best-response rounds | 22.1% | 27.3% | 28.2% | 22.4% |

In the simulator, `--rules house` turns on the first four rules below. The other three are always on.

## Only Fighters use Magic Swords

Only a Fighter adds a Magic Sword's bonus to attack rolls, and only a Fighter can use a sword against a monster with a "–" (counting it as 13). Any other Hero who finds a sword keeps it as treasure: it counts toward their gold, but gives no bonus.

## Hourglass tokens instead of losing turns

Nobody ever loses a turn. Whenever a rule says you lose a turn, take 1 Hourglass token for each turn instead: 1 for a Hurt result (fight-back roll 8–10), and 1 or 2 for a Cage Trap. You still drop your Treasure card and move back 1 space when Hurt.

Each Hourglass token takes 1 off every attack roll you make, spells included. Each fight you win gives back 1 token. A Crushed Hero starts over with none. The same rule applies to every Hero, Fighters included.

## Seriously Hurt doesn't send you home

A Seriously Hurt Hero (fight-back roll 11) still drops half their Treasure cards, but takes 2 Hourglass tokens and moves back 1 space, just as when Hurt, instead of going back to the Great Hall.

## Drop Treasure of your choice

Whenever a monster's fight-back makes you drop Treasure cards (1 card when Stunned or Hurt, half your cards when Seriously Hurt), you choose which cards to drop instead of drawing them at random. This applies to every Hero. A Crushed Hero still drops everything.

Treasure card backs show their level, so a random draw from a face-down hand never hid anything anyway.

## Only 12 numbered slots

A monster that isn't defeated takes a numbered slot if one of the 12 is free. It doesn't matter whether it survived a fight, a missed Fireball or Lightning Bolt from the doorway, or an ESP peek. The same rule applies to every Hero.

If all 12 slots are taken, there's no room:

- **The monster is discarded** to its level's discard pile, every time.
- **Dropped treasure from that fight goes under a monster of the player's choice**: whichever monster already waiting in a slot they pick.
- **The room or chamber stays undefeated**, with no Defeated token. The next Hero to enter draws a new Monster card from that level's pile.
- **A discarded card returns only after a reshuffle**: when that level's pile runs out and the discards are shuffled back in.

In the simulator this is `Game.park` in `sim.py`.

## A Crushed Wizard gets a new spellbook

When a Wizard is Crushed and comes back as a Wizard, they fill a new spellbook, just as at the start of the game: roll 1 die and add 6, then pick that many Spell cards. They pick only from Spell cards that aren't in another Wizard's spellbook.

## Collect all dropped treasure

When you defeat a monster, you collect every Treasure card dropped under it, in a room or a chamber, including cards you dropped yourself.

## An idea, not adopted: a perk for clearing a level

Whoever defeats the last monster in a level's colored rooms (chambers don't count) gets a reward. It's fun, but it doesn't help balance: only Levels 1 and 2 ever get cleared (in about half and a third of games), and the Rogue or Cleric does over 85% of the clearing, so the perk goes to the classes that already win most. Tested on top of the rules above (`--rules house+clear_perk=...`):

| | Rogue | Cleric | Fighter | Wizard | Worst gap |
|---|---|---|---|---|---|
| No perk (the rules above) | 25.9% | 25.4% | 23.7% | 25.0% | 1.3% |
| Draw a Treasure card from the next level down (`deeper`) | 28.5% | 26.7% | 21.5% | 23.3% | 3.5% |
| The same, only for a level shallower than your safest levels (`shallow`) | 25.4% | 26.6% | 23.4% | 24.6% | 1.6% |
| Give back all your Hourglass tokens (`tokens`) | 26.1% | 25.8% | 23.6% | 24.6% | 1.4% |

The bonus card is too generous. The two lighter versions are too small to matter. If your table wants one anyway, either light version is harmless.
