# Replacing "random" drops and Lose a Turn

Two printed mechanics don't play well at the table:

- **"Random" treasure drops.** Treasure card backs differ by level, so shuffling a hand face down doesn't hide anything.
- **Lose a Turn** (a Hurt result of 8–10, and the Cage Trap). Skipping a turn is dull; a perk or a penalty is better.

This page compares the candidate replacements. Drop Treasure of your choice (`choice`) is now a house rule (see `house-rules.md`). No Lose a Turn replacement is adopted yet.

## How it was tested

Each variant was played in 24,000 simulated 4-player games, one Hero of each class, where every player picks a random human-like play style (`python3 explore.py mixed RULES`). Every variant starts from the house rules (see `house-rules.md`) as they were before Drop Treasure of your choice was adopted, so with random drops, unless noted.

Every number moves about ±0.6% between runs from chance alone, so differences under about 1 point are noise. "Worst gap" is how far the furthest class is from an even 25%.

## "Random" drops (`--rules house+drop_pick=...`)

| | Rogue | Cleric | Fighter | Wizard | Worst gap |
|---|---|---|---|---|---|
| Truly random (baseline) | 25.3% | 27.9% | 22.9% | 23.9% | 2.9% |
| Roll a die, count along the row (`die`) | 24.9% | 28.0% | 23.4% | 23.6% | 3.0% |
| Left player picks by card back (`left`) | 24.1% | 28.2% | 22.6% | 25.1% | 3.2% |
| Drop your newest card (`newest`) | 25.0% | 28.4% | 22.3% | 24.4% | 3.4% |
| Drop your lowest-level card (`lowest`) | 25.6% | 29.2% | 22.9% | 22.3% | 4.2% |
| Drop cards of your choice (`choice`) | 26.4% | 28.8% | 23.5% | 21.2% | 3.8% |

- **The die roll plays the same as truly random**, so it fixes the face-down problem without changing balance.
- **The left player picking** helps the Wizard a little, who holds few cards and deep ones.
- **Lowest card** is a perk that helps the Cleric most and costs the Wizard about 2 points.
- **Your choice** is the same kind of perk, applied to both the 1-card drop and the half drop, for every class. It costs the Wizard nearly 3 points and shortens games by about 1 round.

### Drop of your choice under the printed rules (`--rules drop_pick=choice`)

| | Rogue | Cleric | Fighter | Wizard | Worst gap |
|---|---|---|---|---|---|
| Printed rules, truly random drops | 31.5% | 33.6% | 15.7% | 19.2% | 9.3% |
| Printed rules, drops of your choice | 33.2% | 33.8% | 15.3% | 17.6% | 9.7% |

Choosing your drops doesn't fix the printed game; it widens the Rogue and Cleric lead slightly.

## Lose a Turn (`--rules house+lose=...`)

A Hurt Fighter still skips the penalty, as in the current house rules.

| | Rogue | Cleric | Fighter | Wizard | Worst gap | Avg. rounds |
|---|---|---|---|---|---|---|
| Lose a turn (baseline) | 25.3% | 27.9% | 22.9% | 23.9% | 2.9% | 36.0 |
| Drop 1 extra treasure (`extra`) | 23.5% | 27.7% | 22.2% | 26.5% | 2.8% | 36.8 |
| Knocked back 5 spaces toward the Great Hall (`knock`) | 25.5% | 28.7% | 23.9% | 21.8% | 3.7% | 34.7 |
| Wound: −1 on your next attack roll (`wound`) | 26.2% | 28.6% | 22.7% | 22.5% | 3.6% | 35.2 |
| Limp: next turn move, but don't fight (`limp`) | 25.2% | 28.8% | 23.5% | 22.4% | 3.8% | 35.5 |
| Slow: next turn move only 2 (`slow`) | 25.6% | 31.6% | 20.5% | 22.3% | 6.6% | 34.6 |
| Every opponent moves 2 spaces (`rush`) | 26.8% | 31.9% | 21.8% | 19.5% | 6.9% | 33.1 |

- **Drop 1 extra treasure** is the only replacement as balanced as losing a turn. It's a penalty, not a perk, and helps the Wizard.
- **Knock back, Wound, and Limp** are close behind (worst gap 3.6–3.8%), cost the Wizard 1–2 points, and shorten games by about 1 round.
- **Slow and "every opponent moves 2"** clearly unbalance the game.

## Without the Fighter exemption (`--rules swords=fighter+lose=...`)

| | Rogue | Cleric | Fighter | Wizard | Worst gap |
|---|---|---|---|---|---|
| Wound | 27.3% | 29.4% | 20.4% | 22.9% | 4.6% |
| Knocked back 5 | 27.0% | 29.8% | 20.7% | 22.5% | 4.8% |
| Limp | 26.4% | 30.1% | 20.3% | 23.2% | 5.1% |
| Drop 1 extra treasure | 23.9% | 28.2% | 20.8% | 27.1% | 4.2% |
| Every opponent moves 2 | 27.6% | 31.7% | 21.4% | 19.3% | 6.7% |

Every replacement puts the Fighter at 20–21%, so a Hurt Fighter should still skip the penalty, whichever one is picked.

## How the simulator plays each one

- **Die roll:** the hand is laid face up in the order the cards were collected, and the count wraps around. With more than 6 cards, the newest ones can't be picked.
- **Left player:** picks the deepest card back.
- **Your choice:** you give up your cheapest cards first, keeping your wielded Magic Sword and any ESP, Crystal Ball, and Secret Door cards for last, whatever they're worth.
- **Drop half (Seriously Hurt):** the same rule picks each card in turn. Crushed still drops everything.
- **Cage Trap:** losing 1 or 2 turns becomes 1 or 2 penalties.
- **Extra drop from a Cage Trap:** the room is cleared by then, so the card goes to the bottom of its level's treasure pile.
- **Knock back:** moves only through cleared spaces. Hurt still steps you back 1 space first.
- **Opponents' 2 moves:** they move toward their targets but don't fight.
- **AI awareness:** the AI players account for which card a drop takes and for the extra drop. They don't plan around the other penalties.

Not yet run: a drop rule and a lose rule together, or `explore.py adapt` (each class switching to its best strategy) under a replacement.
