#!/usr/bin/env python3
"""
Flight Rising Glimmer & Gloom manual helper / click-through tracking overlay solver.

This version does NOT click tiles.
Instead, it:
1. reads the board,
2. computes the solution,
3. draws red dots over the tiles you should click manually.

Requirements:
    pip install pyautogui pillow mss

Calibration:
    python dots.py --calibrate

Show hints as red dots:
    python dots.py --win light

Overlay controls:
- click tiles normally in the game; a dot disappears when your click lands inside the matching hex tile,
- R = hide old dots, read the board again, and recalculate the solution from the current board,
- after all dots are clicked, after the board looks solved, or when at most 3 dots remain, the program waits for you to click Play Again; if a new board appears, it shows new dots,
- press Enter in the console or Esc to close the overlay.

Important: the overlay does NOT click for you. Your physical click goes to the game only once.
"""

from __future__ import annotations

import argparse
import colorsys
import ctypes
import json
import math
import sys
import threading
import time
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

import pyautogui
from PIL import Image

try:
    import mss
except ImportError:
    mss = None

try:
    import tkinter as tk
except ImportError:
    tk = None

ROW_LENGTHS = [5, 6, 7, 8, 9, 8, 7, 6, 5]
CONFIG_PATH = Path.home() / ".glimmer_gloom_calibration.json"

CONTROL_X = 30
CONTROL_Y = 30
NEW_BOARD_POLL = 0.75
REFRESH_READ_DELAY = 0.15

Point = Tuple[float, float]


# ---------------------------
# Board reading / solving
# ---------------------------

def wait_for_enter(prompt: str) -> None:
    input(prompt + "  [Enter]")


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
    if mss is not None:
        with mss.mss() as sct:
            monitor = sct.monitors[0]
            shot = sct.grab(monitor)
            img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
            return img, int(monitor["left"]), int(monitor["top"])

    img = pyautogui.screenshot().convert("RGB")
    return img, 0, 0


def calibrate(config_path: Path = CONFIG_PATH) -> List[List[Point]]:
    print("\nGlimmer & Gloom board calibration.")
    print("Make sure the whole board is visible, and do not change zoom/scroll after calibration.")
    print("For each row, point to the center of the first and last tile.")
    print("Rows are counted from top to bottom.")
    print(f"Rows: {ROW_LENGTHS}\n")

    if mss is None:
        print("WARNING: mss is not installed. Screen reading may not work correctly with multiple monitors.")
        print("Install it with: pip install mss\n")

    rows: List[List[Point]] = []
    for r, count in enumerate(ROW_LENGTHS, start=1):
        wait_for_enter(f"Row {r}/9 ({count} tiles): move the mouse to the CENTER of the first tile on the left.")
        first = pyautogui.position()
        wait_for_enter(f"Row {r}/9 ({count} tiles): move the mouse to the CENTER of the last tile on the right.")
        last = pyautogui.position()
        rows.append(interpolate((first.x, first.y), (last.x, last.y), count))

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
    config_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nSaved calibration: {config_path}")
    print(f"Screenshot: size={img.size}, left={left}, top={top}")
    return rows


def load_calibration(config_path: Path = CONFIG_PATH) -> List[List[Point]]:
    if not config_path.exists():
        print(f"No calibration file found: {config_path}")
        print("First run: python dots.py --calibrate")
        sys.exit(2)

    payload = json.loads(config_path.read_text(encoding="utf-8"))
    if payload.get("row_lengths") != ROW_LENGTHS:
        print("The calibration file uses an old or different row layout.")
        print("Run again: python dots.py --calibrate")
        sys.exit(2)

    return [[(float(x), float(y)) for x, y in row] for row in payload["rows"]]


def flatten(rows: Sequence[Sequence[Point]]) -> List[Point]:
    return [p for row in rows for p in row]


def average_rgb(img: Image.Image, left: int, top: int, x: float, y: float, radius: int = 7) -> Tuple[int, int, int, int, int]:
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
        raise RuntimeError(
            f"Could not sample pixels: global=({x:.1f},{y:.1f}), mapped=({xi},{yi}), screenshot={img.size}, offset=({left},{top})"
        )

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
    r, g, b = rgb

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
        r, g, b, sx, sy = average_rgb(img, left, top, x, y)
        colors.append(classify_tile((r, g, b)))

    return colors


def print_board(colors: Sequence[str]) -> None:
    i = 0
    max_len = max(ROW_LENGTHS)
    for count in ROW_LENGTHS:
        row = colors[i:i + count]
        i += count
        pad = " " * (max_len - count)
        print(pad + " ".join("L" if c == "light" else "S" for c in row))


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
            raise RuntimeError("No solution exists for the detected board. Calibrate again or check that the board is fully visible.")

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


# ---------------------------
# Overlay drawing
# ---------------------------

def make_click_through(window: tk.Toplevel) -> None:
    if sys.platform != "win32":
        return

    window.update_idletasks()
    hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
    GWL_EXSTYLE = -20
    WS_EX_LAYERED = 0x00080000
    WS_EX_TRANSPARENT = 0x00000020
    WS_EX_TOOLWINDOW = 0x00000080
    style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    style |= WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW
    ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)


def median(values: Sequence[float]) -> float:
    cleaned = sorted(v for v in values if math.isfinite(v) and v > 0)
    if not cleaned:
        return 0.0
    return cleaned[len(cleaned) // 2]


def estimate_hex_geometry(points: Sequence[Point]) -> Tuple[str, float]:
    """
    Estimate a regular hex hit area from the calibrated tile centers.

    The game board is not clicked by this script, but the overlay needs to know
    when the user's manual click belongs to a marked tile. A simple circle around
    the center is not ideal for hexes, so this uses the row spacing to estimate a
    pointy-top or flat-top hex and then tests clicks against that polygon.
    """
    rows: List[List[Point]] = []
    index = 0
    for count in ROW_LENGTHS:
        rows.append(list(points[index:index + count]))
        index += count

    dx_values: List[float] = []
    for row in rows:
        for a, b in zip(row, row[1:]):
            dx_values.append(abs(b[0] - a[0]))

    row_y = [sum(y for _, y in row) / len(row) for row in rows if row]
    dy_values = [abs(b - a) for a, b in zip(row_y, row_y[1:])]

    dx = median(dx_values)
    dy = median(dy_values)
    spacing = nearest_spacing(points)

    if dx <= 0 and dy <= 0:
        return "pointy", max(1.0, spacing * 0.60)

    # Pointy-top hexes usually have vertical row spacing smaller than horizontal
    # center spacing. Flat-top hexes usually have the opposite relation.
    if dy <= dx * 1.05:
        candidates = []
        if dx > 0:
            candidates.append(dx / math.sqrt(3))
        if dy > 0:
            candidates.append(dy / 1.5)
        radius = median(candidates) or spacing * 0.58
        return "pointy", radius * 1.12

    candidates = []
    if dx > 0:
        candidates.append(dx / 1.5)
    if dy > 0:
        candidates.append(dy / math.sqrt(3))
    radius = median(candidates) or spacing * 0.58
    return "flat", radius * 1.12


def hex_vertices(center: Point, orientation: str, radius: float) -> List[Point]:
    cx, cy = center
    start_degrees = -90 if orientation == "pointy" else 0
    vertices = []
    for i in range(6):
        angle = math.radians(start_degrees + i * 60)
        vertices.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
    return vertices


def point_on_segment(px: float, py: float, ax: float, ay: float, bx: float, by: float, eps: float = 1e-6) -> bool:
    cross = (px - ax) * (by - ay) - (py - ay) * (bx - ax)
    if abs(cross) > eps:
        return False
    dot = (px - ax) * (px - bx) + (py - ay) * (py - by)
    return dot <= eps


def point_in_polygon(x: float, y: float, vertices: Sequence[Point]) -> bool:
    inside = False
    n = len(vertices)

    for i in range(n):
        x1, y1 = vertices[i]
        x2, y2 = vertices[(i + 1) % n]

        if point_on_segment(x, y, x1, y1, x2, y2):
            return True

        intersects = ((y1 > y) != (y2 > y)) and (
            x < (x2 - x1) * (y - y1) / ((y2 - y1) or 1e-12) + x1
        )
        if intersects:
            inside = not inside

    return inside


def show_overlay(
    points: Sequence[Point],
    initial_click_points: Sequence[Tuple[int, Point]],
    win_color: str,
    dot_size: int,
    auto_close: float,
    play_again_wait: float,
    play_again_delay: float,
) -> None:
    if tk is None:
        raise RuntimeError("Tkinter is not available. On Windows, it should be included with Python.")

    root = tk.Tk()
    root.withdraw()

    close_event = threading.Event()
    lock = threading.Lock()

    # key = tile index, value = dot window
    windows_by_tile: Dict[int, tk.Toplevel] = {}
    point_by_tile: Dict[int, Point] = {i: p for i, p in enumerate(points)}
    hex_orientation, hex_radius = estimate_hex_geometry(points)
    fallback_click_distance = nearest_spacing(points) * 0.65
    remaining = {"count": 0}
    state = {"refreshing": False, "waiting_for_new_board": False}

    def wait_input() -> None:
        try:
            input(
                "\nOverlay is active. Click tiles normally in the game. "
                "R = refresh/recalculate. Enter closes the overlay...\n"
            )
        except EOFError:
            pass
        close_event.set()

    threading.Thread(target=wait_input, daemon=True).start()

    ctrl = tk.Toplevel(root)
    ctrl.title("G&G overlay")
    ctrl.attributes("-topmost", True)
    ctrl.geometry(f"430x115+{CONTROL_X}+{CONTROL_Y}")

    status_var = tk.StringVar(value="Loading dots...")
    tk.Label(ctrl, textvariable=status_var, justify="center").pack(expand=True, fill="both")
    ctrl.bind("<Escape>", lambda event: close_event.set())

    transparent_bg = "#ff00ff"
    r = dot_size // 2
    outline = max(2, dot_size // 10)

    def solve_current_board() -> List[Tuple[int, Point]]:
        colors = read_board(points)

        rhs = [1 if color != win_color else 0 for color in colors]
        bad_count = sum(rhs)
        print(f"Board read. Tiles to change: {bad_count}. Target: {win_color}.")

        if bad_count == 0:
            return []

        matrix = build_toggle_matrix(points)
        solution = solve_gf2_min_clicks(matrix, rhs, len(points))
        return [(i, points[i]) for i, bit in enumerate(solution) if bit]

    def destroy_all_dots() -> None:
        with lock:
            wins = list(windows_by_tile.values())
            windows_by_tile.clear()
            remaining["count"] = 0

        for win in wins:
            try:
                win.destroy()
            except Exception:
                pass

    def draw_solution(click_points: Sequence[Tuple[int, Point]]) -> None:
        destroy_all_dots()

        with lock:
            remaining["count"] = len(click_points)

        if len(click_points) == 0:
            status_var.set(
                "The board looks solved.\n"
                f"Waiting {play_again_wait:.0f}s for Play Again...\n"
                "R = refresh now, Esc/Enter = close."
            )
            start_wait_for_new_board()
            return

        status_var.set(
            f"Dots remaining: {len(click_points)}\n"
            "Click tiles in the game. R = refresh/recalculate.\n"
            "Esc or Enter in the console = close."
        )

        for order, (index0, (x, y)) in enumerate(click_points, start=1):
            left = int(round(x)) - r
            top = int(round(y)) - r

            win = tk.Toplevel(root)
            win.overrideredirect(True)
            win.attributes("-topmost", True)
            win.configure(bg=transparent_bg)
            try:
                win.wm_attributes("-transparentcolor", transparent_bg)
            except tk.TclError:
                pass
            win.geometry(f"{dot_size}x{dot_size}+{left}+{top}")

            canvas = tk.Canvas(win, width=dot_size, height=dot_size, bg=transparent_bg, highlightthickness=0)
            canvas.pack()
            canvas.create_oval(
                outline,
                outline,
                dot_size - outline,
                dot_size - outline,
                fill="red",
                outline="white",
                width=max(1, outline // 2),
            )

            with lock:
                windows_by_tile[index0] = win

            # The dot does not capture the click. The click goes through to the game.
            try:
                make_click_through(win)
            except Exception:
                pass

    def refresh_solution(reason: str = "manual") -> None:
        if close_event.is_set():
            return
        if state["refreshing"]:
            return

        state["refreshing"] = True
        state["waiting_for_new_board"] = False

        # Important fix:
        # before taking a screenshot, remove old red dots; otherwise the program reads
        # its own overlay as part of the board and calculate the wrong solution.
        destroy_all_dots()
        status_var.set("Old dots are hidden. The board will be read and recalculated shortly...")

        def worker() -> None:
            try:
                time.sleep(REFRESH_READ_DELAY)
                new_click_points = solve_current_board()
                root.after(0, lambda: draw_solution(new_click_points))
            except Exception as exc:
                root.after(0, lambda: status_var.set(f"Refresh error: {exc}\nEsc/Enter = close"))
            finally:
                root.after(0, lambda: state.__setitem__("refreshing", False))

        threading.Thread(target=worker, daemon=True).start()

    def remove_dot_by_tile(tile_index: int) -> None:
        with lock:
            win = windows_by_tile.pop(tile_index, None)
            if win is None:
                return
            remaining["count"] -= 1
            left_count = remaining["count"]

        try:
            win.destroy()
        except Exception:
            pass

        if left_count > 0:
            status_var.set(
                f"Dots remaining: {left_count}\n"
                "Click tiles in the game. R = refresh/recalculate.\n"
                "Esc or Enter in the console = close."
            )
            if left_count <= 3:
                root.after(700, maybe_wait_for_play_again_if_only_few_dots_left)
        else:
            status_var.set(
                "All dots clicked.\n"
                f"Waiting {play_again_wait:.0f}s for Play Again...\n"
                "R = refresh now, Esc/Enter = close."
            )
            start_wait_for_new_board()

    def nearest_remaining_tile(x: float, y: float) -> int | None:
        with lock:
            items = list(windows_by_tile.keys())

        containing: List[Tuple[float, int]] = []
        nearest_idx = None
        nearest_dist = float("inf")

        for idx in items:
            center = point_by_tile[idx]
            dist = math.hypot(x - center[0], y - center[1])
            if dist < nearest_dist:
                nearest_dist = dist
                nearest_idx = idx

            vertices = hex_vertices(center, hex_orientation, hex_radius)
            if point_in_polygon(x, y, vertices):
                containing.append((dist, idx))

        if containing:
            containing.sort()
            return containing[0][1]

        # Small tolerance fallback for imperfect calibration or browser scaling.
        if nearest_idx is not None and nearest_dist <= fallback_click_distance:
            return nearest_idx

        return None

    def board_visibility_and_bad_count() -> Tuple[float, int]:
        """
        Returns (visible_ratio, bad_count).

        visible_ratio tells what fraction of calibration points looks like real
        Glimmer/Gloom tiles. This prevents reading a transition image, reward screen,
        or background after Play Again as if it were a board.
        """
        img, left, top = grab_screen()
        visible = 0
        bad_count = 0

        for x, y in points:
            r, g, b, sx, sy = average_rgb(img, left, top, x, y)
            h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
            hue = h * 360

            looks_light = s > 0.12 and v > 0.20 and 15 <= hue <= 90
            looks_shadow = s > 0.12 and v > 0.20 and 205 <= hue <= 330

            # Fallback based on distance from typical colors, with a brightness limit,
            # so black/background pixels are not treated as tiles.
            yellow = (241, 194, 50)
            purple = (103, 78, 167)
            dy = sum(((r, g, b)[i] - yellow[i]) ** 2 for i in range(3))
            dp = sum(((r, g, b)[i] - purple[i]) ** 2 for i in range(3))
            close_to_tile_color = v > 0.18 and min(dy, dp) < 12000

            is_visible_tile = looks_light or looks_shadow or close_to_tile_color

            if is_visible_tile:
                visible += 1

            color = classify_tile((r, g, b))
            if color != win_color:
                bad_count += 1

        return visible / max(1, len(points)), bad_count

    def start_wait_for_new_board() -> None:
        if state["waiting_for_new_board"] or close_event.is_set():
            return

        state["waiting_for_new_board"] = True
        deadline = time.time() + max(0.0, play_again_wait)

        def worker() -> None:
            while not close_event.is_set() and state["waiting_for_new_board"] and time.time() < deadline:
                time.sleep(NEW_BOARD_POLL)

                try:
                    visible_ratio, bad_count = board_visibility_and_bad_count()
                except Exception:
                    continue

                # bad_count > 0 is not enough, because the program could read a transition
                # image as a board. Require most points to look like real
                # yellow/purple tiles.
                board_visible = visible_ratio >= 0.82
                looks_like_new_puzzle = board_visible and bad_count >= 4

                if looks_like_new_puzzle:
                    root.after(
                        0,
                        lambda vr=visible_ratio, bc=bad_count: status_var.set(
                            f"Detected a probable new board ({vr:.0%} tiles, {bc} to change).\n"
                            f"Waiting {play_again_delay:.1f}s, then checking again..."
                        ),
                    )

                    # Important: first wait, then check again, then calculate.
                    # Do not calculate from the first screenshot; it may be from an animation.
                    time.sleep(max(0.0, play_again_delay))

                    try:
                        visible_ratio2, bad_count2 = board_visibility_and_bad_count()
                    except Exception:
                        continue

                    if visible_ratio2 < 0.82 or bad_count2 < 4:
                        # This was a transition screen/image or the board was not ready yet.
                        # Go back to watching.
                        continue

                    state["waiting_for_new_board"] = False

                    try:
                        # Same as with R: remove old dots before the actual calculation,
                        # so the screenshot does not include the overlay.
                        root.after(0, destroy_all_dots)
                        time.sleep(REFRESH_READ_DELAY)
                        new_click_points = solve_current_board()
                        root.after(0, lambda points_to_draw=new_click_points: draw_solution(points_to_draw))
                    except Exception as exc:
                        root.after(0, lambda error=exc: status_var.set(f"Error after Play Again: {error}\nR = try refreshing, Esc/Enter = close"))
                    return

                remaining_seconds = max(0, int(round(deadline - time.time())))
                root.after(
                    0,
                    lambda s=remaining_seconds: status_var.set(
                        "The board looks solved.\n"
                        f"Waiting for Play Again: {s}s\n"
                        "R = refresh now, Esc/Enter = close."
                    ),
                )

            if not close_event.is_set() and state["waiting_for_new_board"]:
                state["waiting_for_new_board"] = False
                root.after(
                    0,
                    lambda: status_var.set(
                        "No new board was detected after Play Again.\n"
                        "R = try refreshing, Esc/Enter = close."
                    ),
                )

        threading.Thread(target=worker, daemon=True).start()

    def maybe_wait_for_play_again_if_only_few_dots_left() -> None:
        """
        Practical fallback: when at most 3 dots remain, start watching for
        Play Again in the background, but do NOT remove those dots automatically.
        If it was a false alarm, press R to recalculate dots from the current board.
        """
        if close_event.is_set() or state["waiting_for_new_board"] or state["refreshing"]:
            return

        with lock:
            left_count = remaining["count"]

        if left_count <= 3:
            def ui() -> None:
                # Do not remove the last dots. They should still disappear only after clicks.
                status_var.set(
                    f"There are {left_count} dots left. They will stay on screen, but I am already watching for Play Again.\n"
                    f"If you click Play Again within {play_again_wait:.0f}s, I will show new dots.\n"
                    "R = refresh/recalculate, Esc/Enter = close."
                )
                start_wait_for_new_board()

            root.after(0, ui)

    def check_if_board_solved_after_click() -> None:
        """
        Fallback check after a click: if a dot did not disappear,
        but the game is actually solved, do not get stuck on that dot.
        """
        if close_event.is_set() or state["waiting_for_new_board"] or state["refreshing"]:
            return

        def worker() -> None:
            # Short pause for the animation after a tile click.
            time.sleep(0.35)

            if close_event.is_set() or state["waiting_for_new_board"]:
                return

            try:
                colors = read_board(points)
                rhs = [1 if color != win_color else 0 for color in colors]
                bad_count = sum(rhs)
            except Exception:
                return

            if bad_count == 0:
                def solved_ui() -> None:
                    destroy_all_dots()
                    status_var.set(
                        "The board looks solved.\n"
                        f"Waiting {play_again_wait:.0f}s for Play Again...\n"
                        "R = refresh now, Esc/Enter = close."
                    )
                    start_wait_for_new_board()

                root.after(0, solved_ui)

        threading.Thread(target=worker, daemon=True).start()

    def global_mouse_watcher() -> None:
        """
        Windows-only global click watcher.

        The overlay is click-through, so the user's physical click goes to the game normally.
        The watcher does not click anything; it only removes a dot.

        It removes a dot if the start OR end of the click was close to a solution tile.
        """
        if sys.platform != "win32":
            return

        user32 = ctypes.windll.user32
        VK_LBUTTON = 0x01
        was_down = False
        down_pos: Tuple[float, float] | None = None

        while not close_event.is_set():
            down = bool(user32.GetAsyncKeyState(VK_LBUTTON) & 0x8000)

            if down and not was_down:
                pos = pyautogui.position()
                down_pos = (float(pos.x), float(pos.y))

            if was_down and not down:
                up = pyautogui.position()
                up_pos = (float(up.x), float(up.y))

                idx = None
                if down_pos is not None:
                    idx = nearest_remaining_tile(down_pos[0], down_pos[1])
                if idx is None:
                    idx = nearest_remaining_tile(up_pos[0], up_pos[1])

                if idx is not None:
                    root.after(0, lambda tile_index=idx: remove_dot_by_tile(tile_index))

                # Even if the dot was not hit/removed, check
                # whether the board has actually already been solved.
                check_if_board_solved_after_click()

                # If we are stuck with at most 3 dots, do not block Play Again.
                root.after(900, maybe_wait_for_play_again_if_only_few_dots_left)

                down_pos = None

            was_down = down
            time.sleep(0.02)

    def global_keyboard_watcher() -> None:
        if sys.platform != "win32":
            return

        user32 = ctypes.windll.user32
        keys = {
            "R": 0x52,
            "ESC": 0x1B,
        }
        was_down = {name: False for name in keys}

        while not close_event.is_set():
            for name, vk in keys.items():
                down = bool(user32.GetAsyncKeyState(vk) & 0x8000)

                if down and not was_down[name]:
                    if name == "ESC":
                        close_event.set()
                    elif name == "R":
                        root.after(0, lambda: refresh_solution("manual"))

                was_down[name] = down

            time.sleep(0.04)

    # Initial solution
    draw_solution(initial_click_points)

    threading.Thread(target=global_mouse_watcher, daemon=True).start()
    threading.Thread(target=global_keyboard_watcher, daemon=True).start()

    def poll_close() -> None:
        if close_event.is_set():
            try:
                ctrl.destroy()
            except Exception:
                pass

            destroy_all_dots()
            root.quit()
            return

        root.after(100, poll_close)

    root.after(100, poll_close)

    if auto_close > 0:
        root.after(int(auto_close * 1000), close_event.set)

    root.mainloop()


# ---------------------------
# Main
# ---------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Glimmer & Gloom manual overlay solver")
    parser.add_argument("--calibrate", action="store_true", help="save the board position")
    parser.add_argument("--win", choices=["light", "shadow"], default="light", help="target color")
    parser.add_argument("--dot-size", type=int, default=22, help="red dot size in pixels")
    parser.add_argument("--auto-close", type=float, default=0.0, help="close the overlay automatically after N seconds; 0 = wait for Enter/Esc")
    parser.add_argument("--play-again-wait", type=float, default=10.0, help="how many seconds to wait for a new board after solving")
    parser.add_argument("--play-again-delay", type=float, default=0.8, help="how long to wait after detecting a new board after Play Again before taking a screenshot and calculating dots")
    args = parser.parse_args()

    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.02

    if mss is None:
        print("The mss library is missing. Install it with: pip install mss")
        return 2

    if args.calibrate:
        calibrate()
        print("Calibration complete. This file only calibrates the board; it will not solve or click the puzzle.")
        return 0

    rows = load_calibration()
    points = flatten(rows)

    expected = sum(ROW_LENGTHS)
    if len(points) != expected:
        raise RuntimeError(f"Invalid number of points in calibration: {len(points)}, expected {expected}.")

    colors = read_board(points)

    rhs = [1 if color != args.win else 0 for color in colors]
    bad_count = sum(rhs)
    print(f"Read {len(points)} tiles. Tiles to change: {bad_count}. Target: {args.win}.")

    if bad_count == 0:
        print("The board already looks solved.")
        return 0

    matrix = build_toggle_matrix(points)
    solution = solve_gf2_min_clicks(matrix, rhs, len(points))

    click_points: List[Tuple[int, Point]] = [
        (i, points[i]) for i, bit in enumerate(solution) if bit
    ]

    print(f"\nMarking {len(click_points)} tiles to click.")
    print("Tile indexes (1-based):", ", ".join(str(i + 1) for i, _ in click_points))
    for order, (idx, (x, y)) in enumerate(click_points, start=1):
        print(f"{order:02d}. tile #{idx + 1:02d} -> ({round(x)}, {round(y)})")

    show_overlay(
        points=points,
        initial_click_points=click_points,
        win_color=args.win,
        dot_size=max(10, args.dot_size),
        auto_close=max(0.0, args.auto_close),
        play_again_wait=max(0.0, args.play_again_wait),
        play_again_delay=max(0.0, args.play_again_delay),
    )

    print("Overlay closed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
