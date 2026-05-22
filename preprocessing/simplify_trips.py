"""Simplify OSRM-snapped trip geometries with Douglas-Peucker.

OSRM's `overview=full` returns hyper-detailed road geometry (3-5 m
between adjacent points). For visualization at city-block zoom levels,
that's overkill — it inflates the JSON file and the GPU vertex count
without visible benefit. This pass collapses straight-line runs while
preserving every meaningful turn.

Tolerance default 30 m: every avenue corner, every cross-street turn is
kept, but a hundred near-collinear points along Lexington Ave between
42nd and 57th collapses to just the endpoints.
"""

import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PATH = ROOT / "data" / "trips.json"

# Meters per degree at Manhattan's latitude (~40.78°N)
M_PER_DEG_LAT = 111000.0
M_PER_DEG_LNG = 111000.0 * math.cos(math.radians(40.78))


def perpendicular_distance_m(p, a, b):
    """Distance from point p to segment a-b, in meters."""
    ax = a[0] * M_PER_DEG_LNG; ay = a[1] * M_PER_DEG_LAT
    bx = b[0] * M_PER_DEG_LNG; by = b[1] * M_PER_DEG_LAT
    px = p[0] * M_PER_DEG_LNG; py = p[1] * M_PER_DEG_LAT
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    nx = ax + t * dx
    ny = ay + t * dy
    return math.hypot(px - nx, py - ny)


def rdp(points, epsilon_m):
    """Iterative Douglas-Peucker on a list of (lng, lat, ts) points.
    Returns a subset preserving indices 0 and N-1 and any points whose
    perpendicular distance to the simplified segment exceeds epsilon_m."""
    if len(points) <= 2:
        return list(range(len(points)))
    keep = [False] * len(points)
    keep[0] = True
    keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        i0, i1 = stack.pop()
        if i1 - i0 < 2:
            continue
        a, b = points[i0], points[i1]
        max_d = -1.0
        max_i = -1
        for i in range(i0 + 1, i1):
            d = perpendicular_distance_m(points[i], a, b)
            if d > max_d:
                max_d = d
                max_i = i
        if max_d > epsilon_m:
            keep[max_i] = True
            stack.append((i0, max_i))
            stack.append((max_i, i1))
    return [i for i, k in enumerate(keep) if k]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=str(DEFAULT_PATH))
    ap.add_argument("--output", default=str(DEFAULT_PATH))
    ap.add_argument("--epsilon", type=float, default=30.0,
                    help="Simplification tolerance in meters.")
    args = ap.parse_args()

    p = Path(args.input)
    if not p.exists():
        sys.exit(f"Input not found: {p}")
    trips = json.loads(p.read_text())

    before_pts = sum(len(t["path"]) for t in trips)
    before_size = p.stat().st_size

    for t in trips:
        path = t["path"]
        if len(path) <= 3:
            continue
        keep_idx = rdp(path, args.epsilon)
        # Re-distribute the original time range linearly across kept waypoints
        # so the animation timing stays smooth.
        start_ts = path[0][2]
        end_ts = path[-1][2]
        new_path = []
        n = len(keep_idx)
        for j, idx in enumerate(keep_idx):
            ts = int(start_ts + (end_ts - start_ts) * j / max(1, n - 1))
            new_path.append([path[idx][0], path[idx][1], ts])
        t["path"] = new_path

    out = Path(args.output)
    out.write_text(json.dumps(trips, separators=(",", ":")))

    after_pts = sum(len(t["path"]) for t in trips)
    after_size = out.stat().st_size

    print(f"Trips: {len(trips):,}")
    print(f"  waypoints  {before_pts:,} -> {after_pts:,}  "
          f"({100 * after_pts / before_pts:.1f}% kept)")
    print(f"  file size  {before_size / 1024:.0f} KB -> {after_size / 1024:.0f} KB  "
          f"({100 * after_size / before_size:.1f}% of original)")
    print(f"  avg per trip  {before_pts / len(trips):.1f} -> {after_pts / len(trips):.1f}")


if __name__ == "__main__":
    main()
