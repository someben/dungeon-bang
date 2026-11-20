# House rules

Our changes to the printed 2014 rules.

## Unbeaten monsters with no dropped treasure are discarded

Every single time a monster is revealed and not defeated, and no treasure is dropped, its card goes to that level's discard pile instead of a numbered slot. This happens every time, not just when the slots run out.

- If the monster hits a Hero who drops treasure, the monster card goes in a numbered slot as normal, with the treasure under it. It waits there until someone defeats it.
- The room or chamber stays undefeated, with no Defeated token. The next Hero to enter draws a new Monster card from that level's pile.
- A discarded card comes back only when that level's pile runs out and the discard pile is reshuffled.

In the simulator this is `Game.park` in `sim.py`.
