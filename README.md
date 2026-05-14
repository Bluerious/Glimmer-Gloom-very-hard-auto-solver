# Flight Rising Glimmer & Gloom Very Hard auto-solver
Simple auto-clicker for Flight Rising minigame one can use to solve Glimmer &amp; Gloom on a very hard level, to earn up to 75k treasure daily 


This repository contains two scripts:

- `bot.py` — automatically solves the board and clicks the required hexes.
- `dots.py` — shows red dots over the hexes you should click manually. It does **not** click the board for you.

Both scripts use the same calibration file:

```text
~/.glimmer_gloom_calibration.json
```

That means you can calibrate once with `bot.py` and then use `dots.py` with the same board calibration.

---

## Requirements

Install Python 3, then install the required packages:

```bash
pip install pyautogui pillow mss
```
If pip is not recognized, use:

```
python -m pip install pyautogui pillow mss
```
For `dots.py`, `tkinter` is also required. On most Windows Python installs it is included by default.

---

## Important safety controls

For `bot.py`:

- Press **F9** to stop the bot.
- Move the mouse to the top-left corner of the screen to trigger the PyAutoGUI failsafe.

For `dots.py`:

- Press **Esc** to close the overlay.
- Press **Enter** in the console to close the overlay.
- Press **R** to refresh the board reading and recalculate the dots.

---

## First-time setup

Open the Glimmer & Gloom board in your browser. Make sure the whole board is visible.

Do not change browser zoom, scroll position, monitor layout, or board position after calibration. If anything changes, run calibration again.

---

# Using `bot.py`

`bot.py` automatically reads the board, calculates the solution, clicks the required hexes, and can click the **Play Again** button between games.

## Calibrate `bot.py`

Run:

```bash
python bot.py --calibrate
```

The script will ask you to point at the center of the first and last hex in each row.

After board calibration, it solves one board so the **Play Again** button appears. Then it asks you to point at the center of the **Play Again** button. This position is saved in the calibration file.

You only need to do this again if the board or button position changes.

## Solve one board

```bash
python bot.py --win light
```

or:

```bash
python bot.py --win shadow
```

## Solve multiple boards

```bash
python bot.py --win light --games 10
```

The bot will solve a board, click **Play Again**, wait for the next board, and continue until it reaches the requested number of games.

---

## `bot.py` arguments

### `--calibrate`

Runs full calibration.

This calibrates:

1. the hex board positions,
2. the **Play Again** button position.

Example:

```bash
python bot.py --calibrate
```

---

### `--win light` / `--win shadow`

Chooses the target color.

Use `light` if the final board should be light/yellow.
Use `shadow` if the final board should be shadow/purple.

Default:

```text
light
```

Examples:

```bash
python bot.py --win light
python bot.py --win shadow
```

---

### `--delay`

Sets the pause between automatic clicks, in seconds.

Default:

```text
0.20
```

Example:

```bash
python bot.py --win light --delay 0.1
```

This means the bot waits about `0.1` seconds between clicks.

---

### `--finish-delay`

Sets how long the bot waits after solving a board before clicking the **Play Again** button.

Default:

```text
0.4
```

Example:

```bash
python bot.py --win light --games 5 --finish-delay 0.6
```

Increase this value if the ending screen appears slowly.

---

### `--games`

Sets how many boards to solve.

Default:

```text
1
```

Example:

```bash
python bot.py --win light --games 10
```

---

### `--next-wait`

Sets how long the bot waits after clicking **Play Again** before reading the next board.

Default:

```text
1.0
```

Example:

```bash
python bot.py --win light --games 10 --next-wait 1.5
```

Increase this value if the next board is not ready when the bot reads it.

---

# Using `dots.py`

`dots.py` is the manual helper.

It does **not** click any hexes. Instead, it reads the board, solves it, and places red dots over the hexes you should click manually.

Examples below use `dots.py`.

## Calibrate only the hex board

```bash
python dots.py --calibrate
```

This only calibrates the hex positions. It does **not** solve the board and does **not** calibrate the **Play Again** button.

You can also skip this if you already calibrated the board with `bot.py`, because both scripts use the same calibration file.

## Show dots for one board

```bash
python dots.py --win light
```

or:

```bash
python dots.py --win shadow
```

Click the marked hexes manually in the game.

The overlay is click-through, so your clicks should go to the game, not to the red dots.

## Refresh the dots

Press:

```text
R
```

This hides the old dots, reads the current board again, recalculates the solution, and draws new dots.

## Continue after Play Again

After the board is solved, click **Play Again** yourself.

`dots.py` waits for a new board. When it detects one, it calculates and shows the next set of dots.

---

## `dots.py` arguments

### `--calibrate`

Calibrates only the hex board positions and exits.

Example:

```bash
python dots.py --calibrate
```

Use this if you want to use the manual helper without running `bot.py` first.

---

### `--win light` / `--win shadow`

Chooses the target color.

Default:

```text
light
```

Examples:

```bash
python dots.py --win light
python dots.py --win shadow
```

---

### `--dot-size`

Sets the size of the red dots in pixels.

Default:

```text
22
```

Example:

```bash
python dots.py --win light --dot-size 28
```

Use a larger value if the dots are hard to see. Use a smaller value if they cover too much of the board.

---

### `--auto-close`

Automatically closes the overlay after a number of seconds.

Default:

```text
0
```

`0` means the overlay stays open until you press **Enter** in the console or **Esc**.

Example:

```bash
python dots.py --win light --auto-close 60
```

---

### `--play-again-wait`

Sets how long `dots.py` waits for a new board after the current one is solved.

Default:

```text
10.0
```

Example:

```bash
python dots.py --win light --play-again-wait 15
```

Increase this if you need more time to click **Play Again** manually.

---

### `--play-again-delay`

Sets how long `dots.py` waits after detecting a new board before taking the screenshot used for the next solution.

Default:

```text
0.8
```

Example:

```bash
python dots.py --win light --play-again-delay 1.2
```

Increase this if the game has a transition animation and dots appear based on an unfinished board.

---

# Recommended commands

## Fully automatic mode

```bash
python bot.py --calibrate
python bot.py --win light --games 10 --delay 0.1
```

## Manual dot-helper mode

```bash
python dots.py --calibrate
python dots.py --win light
```

Or, if you already calibrated with `bot.py`:

```bash
python dots.py --win light
```

---

# Troubleshooting

## The bot clicks in the wrong place

Run calibration again:

```bash
python bot.py --calibrate
```

Make sure the browser zoom, board position, monitor layout, and scroll position stay the same after calibration.

## The first click does not register

Make sure the browser/game window is focused before the bot starts clicking. During calibration, follow the console instructions carefully when it asks you to prepare the game window.

## The next board is read too early

Increase `--next-wait` for `bot.py`:

```bash
python bot.py --win light --games 10 --next-wait 1.5
```

For `dots.py`, increase `--play-again-delay`:

```bash
python dots.py --win light --play-again-delay 1.2
```

## The dots are too small or too large

Change `--dot-size`:

```bash
python dots.py --win light --dot-size 28
```

## Multi-monitor setup does not work correctly

Make sure `mss` is installed:

```bash
pip install mss
```

Then run calibration again.
