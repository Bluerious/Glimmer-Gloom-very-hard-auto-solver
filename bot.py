#!/usr/bin/env python3
"""
Flight Rising Glimmer & Gloom hex Lights Out solver/clicker bot.

This version supports multi-monitor layouts and shifted coordinates by using
mss to capture the entire virtual desktop.

Installation:
    pip install pyautogui pillow mss

Calibration:
    python bot.py --calibrate

Normal run:
    python bot.py --win light
or:
    python bot.py --win shadow

Emergency stop:
    press F9 or move the mouse to the top-left corner of the screen
    (pyautogui FAILSAFE).
"""

from __future__ import annotations

import argparse
import colorsys
import ctypes
import json
import math
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import pyautogui
from PIL import Image

try:
    import mss
except ImportError:
    mss = None

ROW_LENGTHS = [5, 6, 7, 8, 9, 8, 7, 6, 5]
CONFIG_PATH = Path.home() / ".glimmer_gloom_calibration.json"

Point = Tuple[float, float]


class UserAbort(Exception):
    pass


def f9_pressed() -> bool:
    """Windows: F9 aborts the program."""
    if sys.platform != "win32":
        return False
    VK_F9 = 0x78
    return bool(ctypes.windll.user32.GetAsyncKeyState(VK_F9) & 0x8000)


def abort_if_f9() -> None:
    if f9_pressed():
        raise UserAbort("Aborted with F9.")


def sleep_with_abort(seconds: float, step: float = 0.05) -> None:
    end = time.time() + max(0.0, seconds)
    while time.time() < end:
        abort_if_f9()
        time.sleep(min(step, max(0.0, end - time.time())))


def wait_for_enter(prompt: str) -> None:
    input(prompt + "  [Enter]")


FOCUS_DELAY = 0.8


def alt_tab_with_abort() -> None:
    abort_if_f9()
    pyautogui.hotkey("alt", "tab")
    sleep_with_abort(FOCUS_DELAY)


def prepare_game_window_from_console() -> None:
    print(
        "Prepare the browser/game window so it is the previous Alt+Tab window. "
        "Make sure the console is not covering the board after Alt+Tab."
    )
    wait_for_enter("When ready, press Enter here. I will Alt+Tab to the game and start reading/clicking.")
    alt_tab_with_abort()


def return_to_console_from_game() -> None:
    print("Switching back to the console with Alt+Tab...")
    alt_tab_with_abort()


def interpolate(a: Point, b: Point, count: int) -> List[Point]:
    if count == 1:
        return [a]
    ax, ay = a
    bx, by = b
    return [
        (ax + (bx - ax) * i / (count - 1), ay + (by - ay) * i / (count - 1))
        for i in range(count)
    ]


def grab_screen() -> Tuple[Image.Image, int, int]:
    """
    Returns (image, left, top), where left/top are global mouse coordinate offsets.
    mss.monitors[0] is the whole virtual desktop, including side monitors.
    """
    if mss is not None:
        with mss.mss() as sct:
            monitor = sct.monitors[0]
            shot = sct.grab(monitor)
            img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
            return img, int(monitor["left"]), int(monitor["top"])

    # Fallback: primary screen only. This may not be enough for multi-monitor layouts.
    img = pyautogui.screenshot().convert("RGB")
    return img, 0, 0


def save_calibration(rows: List[List[Point]], finish_button: Optional[Point] = None, config_path: Path = CONFIG_PATH) -> None:
    img, left, top = grab_screen()
    payload = {
        "row_lengths": ROW_LENGTHS,
        "screen_size": tuple(pyautogui.size()),
        "screenshot_size": img.size,
        "screenshot_left": left,
        "screenshot_top": top,
        "rows": rows,
        "created_at": time.time(),
    }
    if finish_button is not None:
        payload["finish_button"] = [float(finish_button[0]), float(finish_button[1])]

    config_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nSaved calibration: {config_path}")
    print(f"Screenshot: size={img.size}, left={left}, top={top}")
    if finish_button is not None:
        print(f"Play Again button: ({round(finish_button[0])}, {round(finish_button[1])})")


def calibrate_board() -> List[List[Point]]:
    print("\nGlimmer & Gloom board calibration.")
    print("Make sure the whole board is visible, and do not change zoom/scroll after calibration.")
    print("For each row, point at the center of the first and last tile.")
    print("Rows are counted from top to bottom.")
    print(f"Rows: {ROW_LENGTHS}\n")

    if mss is None:
        print("WARNING: mss is not installed. Multi-monitor reading may not work correctly.")
        print("Install it with: pip install mss\n")

    rows: List[List[Point]] = []
    for r, count in enumerate(ROW_LENGTHS, start=1):
        wait_for_enter(f"Row {r}/9 ({count} tiles): move the mouse to the CENTER of the first tile on the left.")
        first = pyautogui.position()
        wait_for_enter(f"Row {r}/9 ({count} tiles): move the mouse to the CENTER of the last tile on the right.")
        last = pyautogui.position()
        rows.append(interpolate((first.x, first.y), (last.x, last.y), count))

    return rows


def calibrate_finish_button() -> Point:
    print("\nPlay Again / next-game button calibration.")
    print("Move the mouse to the CENTER of the button that appears after the game ends.")
    print("If the browser is still focused, switch back to this console first. Keep the mouse over the button.")
    wait_for_enter("When the cursor is centered on the Play Again button, press Enter in this console.")
    pos = pyautogui.position()
    return (float(pos.x), float(pos.y))


def load_calibration(config_path: Path = CONFIG_PATH) -> Tuple[List[List[Point]], Optional[Point]]:
    if not config_path.exists():
        print(f"Missing calibration: {config_path}")
        print("First run: python bot.py --calibrate")
        sys.exit(2)

    payload = json.loads(config_path.read_text(encoding="utf-8"))
    if payload.get("row_lengths") != ROW_LENGTHS:
        print("The calibration file has an old or different row layout.")
        print("Run again: python bot.py --calibrate")
        sys.exit(2)

    rows = [[(float(x), float(y)) for x, y in row] for row in payload["rows"]]
    finish_raw = payload.get("finish_button")
    finish_button = None
    if isinstance(finish_raw, list) and len(finish_raw) == 2:
        finish_button = (float(finish_raw[0]), float(finish_raw[1]))

    return rows, finish_button


def flatten(rows: Sequence[Sequence[Point]]) -> List[Point]:
    return [p for row in rows for p in row]


def average_rgb(img: Image.Image, left: int, top: int, x: float, y: float, radius: int = 7) -> Tuple[int, int, int, int, int]:
    """
    x/y are global mouse coordinates.
    The mss screenshot has its own left/top offset, so the sample is x-left, y-top.
    """
    xi = int(round(x - left))
    yi = int(round(y - top))

    w, h = img.size
    clipped = False
    if xi < 0 or xi >= w or yi < 0 or yi >= h:
        clipped = True

    xi = max(0, min(w - 1, xi))
    yi = max(0, min(h - 1, yi))

    pixels = []
    for yy in range(max(0, yi - radius), min(h, yi + radius + 1)):
        for xx in range(max(0, xi - radius), min(w, xi + radius + 1)):
            if (xx - xi) ** 2 + (yy - yi) ** 2 <= radius ** 2:
                pixels.append(img.getpixel((xx, yy))[:3])

    if not pixels:
        raise RuntimeError(f"Could not sample pixels: global=({x:.1f},{y:.1f}), mapped=({xi},{yi}), screenshot={img.size}, offset=({left},{top})")

    r = sum(p[0] for p in pixels) / len(pixels)
    g = sum(p[1] for p in pixels) / len(pixels)
    b = sum(p[2] for p in pixels) / len(pixels)

    if clipped:
        print(
            f"WARNING: global point=({x:.1f},{y:.1f}) maps outside the screenshot: "
            f"mapped=({int(round(x-left))},{int(round(y-top))}), screenshot={img.size}, offset=({left},{top})"
        )

    return int(r), int(g), int(b), xi, yi


def classify_tile(rgb: Tuple[int, int, int]) -> str:
    """Returns 'light' for yellow or 'shadow' for purple."""
    r, g, b = rgb

    # If we read an almost-black background, this is probably not a tile.
    # Do not stop the program, but classify it as shadow.
    if r < 35 and g < 35 and b < 35:
        return "shadow"

    h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
    hue = h * 360

    if s > 0.12:
        if 15 <= hue <= 90:
            return "light"
        if 205 <= hue <= 330:
            return "shadow"

    yellow = (241, 194, 50)
    purple = (103, 78, 167)
    dy = sum((rgb[i] - yellow[i]) ** 2 for i in range(3))
    dp = sum((rgb[i] - purple[i]) ** 2 for i in range(3))
    return "light" if dy <= dp else "shadow"


def read_board(points: Sequence[Point]) -> List[str]:
    img, left, top = grab_screen()
    colors: List[str] = []

    for x, y in points:
        r, g, b, _sx, _sy = average_rgb(img, left, top, x, y)
        colors.append(classify_tile((r, g, b)))

    return colors

def nearest_spacing(points: Sequence[Point]) -> float:
    dists = []
    for i, (x1, y1) in enumerate(points):
        best = float("inf")
        for j, (x2, y2) in enumerate(points):
            if i == j:
                continue
            d = math.hypot(x1 - x2, y1 - y2)
            if d < best:
                best = d
        if math.isfinite(best):
            dists.append(best)
    dists.sort()
    return dists[len(dists) // 2]


def build_toggle_matrix(points: Sequence[Point]) -> List[int]:
    n = len(points)
    spacing = nearest_spacing(points)
    threshold = spacing * 1.20

    rows = []
    for i, (x1, y1) in enumerate(points):
        bits = 0
        for j, (x2, y2) in enumerate(points):
            if i == j or math.hypot(x1 - x2, y1 - y2) <= threshold:
                bits |= 1 << j
        rows.append(bits)
    return rows


def rref_gf2(matrix_rows: Sequence[int], rhs: Sequence[int], nvars: int) -> Tuple[List[int], List[int]]:
    rows = [matrix_rows[i] | (int(rhs[i]) << nvars) for i in range(len(matrix_rows))]
    m = len(rows)
    rank = 0
    pivot_cols: List[int] = []

    for col in range(nvars):
        pivot = None
        for r in range(rank, m):
            if (rows[r] >> col) & 1:
                pivot = r
                break
        if pivot is None:
            continue

        rows[rank], rows[pivot] = rows[pivot], rows[rank]

        for r in range(m):
            if r != rank and ((rows[r] >> col) & 1):
                rows[r] ^= rows[rank]

        pivot_cols.append(col)
        rank += 1

    coeff_mask = (1 << nvars) - 1
    for row in rows:
        if (row & coeff_mask) == 0 and ((row >> nvars) & 1):
            raise RuntimeError("No solution for the detected board. Recalibrate and try again.")

    return rows[:rank], pivot_cols


def solve_gf2_min_clicks(matrix_rows: Sequence[int], rhs: Sequence[int], nvars: int) -> List[int]:
    rref_rows, pivot_cols = rref_gf2(matrix_rows, rhs, nvars)
    pivot_set = set(pivot_cols)
    free_cols = [c for c in range(nvars) if c not in pivot_set]

    base = 0
    basis: List[int] = []
    pivot_row_for_col: Dict[int, int] = {col: r for r, col in enumerate(pivot_cols)}

    for col in pivot_cols:
        r = pivot_row_for_col[col]
        if (rref_rows[r] >> nvars) & 1:
            base |= 1 << col

    for free in free_cols:
        vec = 1 << free
        for col in pivot_cols:
            r = pivot_row_for_col[col]
            if (rref_rows[r] >> free) & 1:
                vec |= 1 << col
        basis.append(vec)

    best = base
    best_weight = base.bit_count()

    if len(basis) <= 24:
        total = 1 << len(basis)
        current = base
        previous_gray = 0
        for k in range(1, total):
            gray = k ^ (k >> 1)
            changed = gray ^ previous_gray
            bit = changed.bit_length() - 1
            current ^= basis[bit]
            w = current.bit_count()
            if w < best_weight:
                best = current
                best_weight = w
            previous_gray = gray

    return [(best >> i) & 1 for i in range(nvars)]


def click_solution(points: Sequence[Point], solution: Sequence[int], delay: float) -> None:
    clicks = [(points[i][0], points[i][1]) for i, bit in enumerate(solution) if bit]
    print(f"Clicks to perform: {len(clicks)}")
    print("F9 = abort.")
    sleep_with_abort(0.5)

    for idx, (x, y) in enumerate(clicks, start=1):
        abort_if_f9()
        print(f"Click {idx}/{len(clicks)}: ({round(x)}, {round(y)})")
        pyautogui.click(x, y)
        sleep_with_abort(max(0.0, delay))

def solve_one_board(points: Sequence[Point], args: argparse.Namespace, game_label: str = "Board") -> bool:
    abort_if_f9()
    print(f"\n=== {game_label} ===")

    colors = read_board(points)
    rhs = [1 if color != args.win else 0 for color in colors]
    bad_count = sum(rhs)
    print(f"Detected {len(points)} tiles. Tiles to change: {bad_count}. Target: {args.win}.")

    matrix = build_toggle_matrix(points)
    solution = solve_gf2_min_clicks(matrix, rhs, len(points))
    click_count = sum(solution)

    if bad_count == 0:
        print("The board already looks solved.")
    elif click_count == 0:
        print("The solver sees no clicks to perform, but the board does not look solved.")
        return False
    else:
        click_solution(points, solution, args.delay)
        print("Clicks completed. Skipping board verification because the game shows an ending screen after solving.")

    return True



def main() -> int:
    parser = argparse.ArgumentParser(description="Glimmer & Gloom solver/clicker bot")
    parser.add_argument("--calibrate", action="store_true", help="calibrate the board, solve one board, and save the Play Again button position")
    parser.add_argument("--win", choices=["light", "shadow"], default="light", help="color that should win")
    parser.add_argument("--delay", type=float, default=0.20, help="pause between clicks in seconds")
    parser.add_argument("--finish-delay", type=float, default=0.4, help="seconds to wait after solving before clicking Play Again")
    parser.add_argument("--games", type=int, default=1, help="number of boards to solve in a row")
    parser.add_argument("--next-wait", type=float, default=1.0, help="seconds to wait after clicking Play Again before reading the next board")
    args = parser.parse_args()

    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.02

    if mss is None:
        print("Missing mss library. Install it with: pip install mss")
        return 2

    print("F9 = abort the program.")

    try:
        if args.calibrate:
            rows = calibrate_board()
            points = flatten(rows)

            expected = sum(ROW_LENGTHS)
            if len(points) != expected:
                raise RuntimeError(f"Invalid number of calibration points: {len(points)}, expected {expected}.")

            print("\nI will now solve the current board so the Play Again button appears for calibration.")
            prepare_game_window_from_console()
            solved = solve_one_board(points, args, "Calibration board")
            if not solved:
                print("Could not reach the ending screen, so I will not save the calibration.")
                return 1

            sleep_with_abort(args.finish_delay)
            return_to_console_from_game()
            finish_button = calibrate_finish_button()
            save_calibration(rows, finish_button=finish_button)
            print("Calibration complete. Future runs can use --games without manual button coordinates.")
            return 0

        rows, calibrated_finish = load_calibration()
        points = flatten(rows)

        expected = sum(ROW_LENGTHS)
        if len(points) != expected:
            raise RuntimeError(f"Invalid number of calibration points: {len(points)}, expected {expected}.")

        finish_button = calibrated_finish

        total_games = max(1, args.games)

        for game_no in range(1, total_games + 1):
            solved = solve_one_board(points, args, f"Board {game_no}/{total_games}")
            if not solved:
                return 1

            if game_no < total_games:
                if finish_button is None:
                    print("No calibrated Play Again button found.")
                    print("Run: python bot.py --calibrate")
                    return 2
                sleep_with_abort(args.finish_delay)
                abort_if_f9()
                pyautogui.click(finish_button[0], finish_button[1])
                print(f"Clicked Play Again: ({round(finish_button[0])}, {round(finish_button[1])})")

                print(f"Waiting {args.next_wait:.1f}s before reading the next board...")
                sleep_with_abort(args.next_wait)
            else:
                print("Last board finished — not clicking Play Again.")

        print(f"Finished: solved {total_games} board(s).")
        return 0

    except UserAbort:
        print("Aborted with F9.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
