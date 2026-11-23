# dungeon-bang

A Monte Carlo simulator for the board game **Dungeon!** (2014 Wizards of the Coast edition), used to study class balance: who wins, which strategies work, and which house rules even things out.

This is an unofficial fan project. It is not affiliated with or endorsed by Wizards of the Coast. You need your own copy of the game to play it; the rulebook text and board art are not included here.

## What's here

| File | What it is |
|---|---|
| `sim.py` | The game engine and AI players. `python3 sim.py --games 1000` |
| `explore.py` | Parallel experiments: strategies, best responses, house-rule searches |
| `board.txt` | The board as a graph: every hallway space, room, chamber, door, and secret door |
| `monsters.csv`, `treasures.csv` | Card stats: to-hit numbers per class and spell, treasure values, special effects |
| `house-rules.md` | The six house rules that even out the four classes, with the results |
| `rules.md` | Our summary of the rules and the sim's interpretation of unclear points |
| `tools/` | Board-tracing tools (they need your own photos of the board in `photos/`) |
| `results/explore.jsonl` | Logged experiment results |

## Usage

```
python3 sim.py --games 2000
python3 sim.py --games 2000 --policy ev,ev,lv=3-5,lv=4-6
python3 sim.py --games 2000 --rules house
python3 explore.py rules      # try each house rule
```

Strategies (`--policy`) and house rules (`--rules`) are documented at the top of `sim.py`.
