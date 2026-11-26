# Replacing "random" drops and Lose a Turn

Two printed mechanics don't play well at the table:

- **"Random" treasure drops.** Treasure card backs differ by level, so shuffling a hand face down doesn't hide anything.
- **Lose a Turn** (a Hurt result of 8–10, and the Cage Trap). Skipping a turn is dull; a perk or a penalty is better.

This page compares the candidate replacements. Two are now house rules (see `house-rules.md`): Drop Treasure of your choice (`choice`), and Hourglass tokens that last until you win a fight (`hourglass`), which also replaced "A Hurt Fighter doesn't lose a turn".

## How it was tested

Each variant was played in 24,000 simulated 4-player games, one Hero of each class, where every player picks a random human-like play style (`python3 explore.py mixed RULES`). Every variant starts from the house rules (see `house-rules.md`) as they were before Drop Treasure of your choice was adopted, so with random drops, unless noted. Since `house` now means the adopted rules, rerun the first-round tables with `swords=fighter+f_tough=1` in place of `house`.

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

## Second round: with drops of your choice

These ran after Drop Treasure of your choice was adopted, with the Fighter exemption unless noted (`--rules swords=fighter+f_tough=1+drop_pick=choice+lose=...`).

| | Rogue | Cleric | Fighter | Wizard | Worst gap | Avg. rounds |
|---|---|---|---|---|---|---|
| Lose a turn (baseline) | 26.4% | 28.8% | 23.5% | 21.2% | 3.8% | 34.9 |
| Rest in place, may fight or cast (`rest`, `rest_move=0`, `rest_fight=1`) | 26.4% | 29.0% | 23.6% | 20.9% | 4.1% | 34.8 |
| Rest: move up to 1, no fighting (`rest`, `rest_move=1`) | 26.0% | 28.6% | 24.0% | 21.4% | 3.6% | 34.7 |
| Rest: move up to 2, no fighting (`rest`, `rest_move=2`) | 26.2% | 29.1% | 23.8% | 21.0% | 4.1% | 34.5 |
| Rest: move up to 3, no fighting (`rest`, `rest_move=3`) | 26.2% | 29.1% | 23.9% | 20.9% | 4.1% | 34.5 |
| Rest: move up to 3, may fight (`rest`, `rest_move=3`, `rest_fight=1`) | 28.2% | 32.1% | 19.8% | 19.8% | 7.1% | 33.2 |
| Shaken: +1 on the next fight-back roll (`shaken`) | 27.2% | 30.7% | 21.4% | 20.6% | 5.7% | 33.4 |
| Blessing: every opponent +1 on their next attack (`bless`) | 27.9% | 31.6% | 19.7% | 20.8% | 6.6% | 30.8 |
| Bounty: 1 extra Treasure for whoever beats the monster (`bounty`) | 30.3% | 40.9% | 13.0% | 15.9% | 15.9% | 26.7 |
| Hourglass, gone after your next attack roll (`hourglass=next`) | 26.8% | 29.0% | 23.3% | 20.9% | 4.1% | 34.2 |
| Hourglass, gone when you win a fight (`hourglass=win`) | 24.3% | 25.2% | 28.3% | 22.2% | 3.3% | 35.2 |
| Hourglass, gone in the Great Hall (`hourglass=hall`) | 19.1% | 20.6% | 34.3% | 26.0% | 9.3% | 37.8 |
| Hourglass, never gone (`hourglass=game`) | 16.4% | 18.0% | 40.0% | 25.6% | 15.0% | 39.1 |
| **Without the Fighter exemption** | | | | | | |
| Hourglass, gone when you win a fight (adopted) | 26.3% | 26.6% | 22.1% | 25.0% | 2.9% | 35.8 |
| Hourglass, gone in the Great Hall | 22.0% | 23.5% | 21.9% | 32.6% | 7.6% | 39.4 |

- **Resting** plays like losing a turn as long as you can't fight. How far you may move barely matters.
- **Shaken, Blessing, and Bounty** are too light or too generous, and help the Rogue and Cleric.
- **Hourglass tokens** get harsher the longer they last, which pulls back the Rogue and Cleric, who are Hurt most. With the Fighter exempt, lasting tokens hand the Fighter the game. Without the exemption, tokens that last until you win a fight give the most even split of any rule set tested, and the Wizard's best result.

### A perk for clearing a level (`--rules house+clear_perk=deeper`, with lose a turn and the Fighter exemption)

Whoever puts the Defeated token on a level's last room (chambers don't count) draws a bonus Treasure card. Each level has exactly as many Treasure cards as rooms, so that level's pile is empty by then; the bonus comes from the next level down.

| | Rogue | Cleric | Fighter | Wizard | Worst gap |
|---|---|---|---|---|---|
| Level-clear perk | 29.3% | 29.9% | 21.4% | 19.4% | 5.6% |

Only Levels 1 and 2 ever get cleared (in about half and a third of games), almost always by the Rogue or Cleric, so the perk goes to the leaders.

## Third round: small tweaks on the adopted house rules

Each was screened with mixed human tables and strong play; the best went to a full 24,000-game mixed run and `explore.py adapt` (2 rounds). Numbers are against the house rules as they stood then (`swords=fighter+drop_pick=choice+lose=hourglass+hourglass=win`).

| | Rogue | Cleric | Fighter | Wizard | Worst gap |
|---|---|---|---|---|---|
| **Mixed human tables** | | | | | |
| House rules then | 26.3% | 26.6% | 22.1% | 25.0% | 2.9% |
| Seriously Hurt: 2 tokens, step back (`serious=tokens`) | 26.3% | 26.2% | 23.5% | 23.9% | 1.5% |
| Plus each win gives back 1 token (`hourglass=win1`, adopted) | 25.9% | 25.4% | 23.7% | 25.0% | 1.3% |
| Clearing a chamber pays a Treasure card (`chamber_perk=1`) | 25.5% | 25.8% | 21.2% | 27.5% | 3.8% |
| **After 2 best-response rounds** | | | | | |
| House rules then | 24.4% | 26.5% | 27.6% | 21.6% | 3.4% |
| `serious=tokens` | 22.8% | 27.0% | 28.1% | 22.1% | 3.1% |
| `serious=tokens+hourglass=win1` (adopted) | 22.1% | 27.3% | 28.2% | 22.4% | 3.2% |
| `chamber_perk=1` | 24.0% | 25.7% | 26.5% | 23.9% | 1.5% |

Screened and dropped: Stunned gives a token instead of a drop (`stun=token`), a shortcut from the Great Hall to cleared chambers (`shortcut`), fleeing for a token (`flee`: Fighter 35%), draw 2 keep 1 in deep rooms (`deep_pick`: Wizard 32–39%), +1 for the trailing Hero (`underdog`), +1 deeper than your safest levels (`daring`: Rogue 34–38%), a token or no treasure for shallow wins (`shallow`), moving 10 once you have enough gold (`homeward`), Crushed drops half (`crush=half`), and tokens that also clear in the Great Hall (`hourglass=winhall`).

## How the simulator plays each one

- **Die roll:** the hand is laid face up in the order the cards were collected, and the count wraps around. With more than 6 cards, the newest ones can't be picked.
- **Left player:** picks the deepest card back.
- **Your choice:** you give up your cheapest cards first, keeping your wielded Magic Sword and any ESP, Crystal Ball, and Secret Door cards for last, whatever they're worth.
- **Drop half (Seriously Hurt):** the same rule picks each card in turn. Crushed still drops everything.
- **Cage Trap:** losing 1 or 2 turns becomes 1 or 2 penalties.
- **Extra drop from a Cage Trap:** the room is cleared by then, so the card goes to the bottom of its level's treasure pile.
- **Knock back:** moves only through cleared spaces. Hurt still steps you back 1 space first.
- **Opponents' 2 moves:** they move toward their targets but don't fight.
- **Resting:** a Hurt Hero has already stepped back into the hallway. Resting in place with fighting allowed means fighting the monster in your space, if you couldn't step back, or a Wizard casting next door.
- **Shaken:** the +1 is used by your next melee fight; spells from outside don't use it.
- **Bounty:** a Cage Trap leaves no monster, so it costs nothing. A discarded monster's bounty goes with its dropped treasure.
- **Hourglass:** Crushed clears all tokens. The AI doesn't plan trips home to clear Great Hall tokens.
- **AI awareness:** the AI players account for which card a drop takes and for the extra drop. They don't plan around the other penalties.

Not yet run: `explore.py adapt` (each class switching to its best strategy) under the adopted house rules.
