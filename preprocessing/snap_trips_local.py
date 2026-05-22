"""Snap a 'raw' trips JSON file to real OSM roads using a *local* OSRM
container, with many concurrent requests.

Public OSRM demo: ~1 req/sec — 500k trips would take 6 days.
Local OSRM with asyncio + 32 concurrent workers: 1000+ req/sec — 500k
trips in ~8 minutes.

Input  : data/tiers/trips-{tier}.raw.json   (output of build_trip_tiers.py)
Output : data/tiers/trips-{tier}.json       (full road geometry, simplified)

Run:
    python3 preprocessing/snap_trips_local.py --tier 25k
    python3 preprocessing/snap_trips_local.py --tier 100k
    python3 preprocessing/snap_trips_local.py --tier 500k
    python3 preprocessing/snap_trips_local.py --tier 2m

Requires an OSRM router running on localhost:5000 with the NYC area
loaded (see preprocessing/setup_osrm.sh).
"""

import argparse
import asyncio
import json
import math
import sys
import time
from pathlib import Path

import aiohttp

ROOT = Path(__file__).resolve().parent.parent

# Douglas-Peucker simplification tolerance for the snapped path.
SIMPLIFY_EPSILON_M = 30.0
M_PER_DEG_LAT = 111000.0
M_PER_DEG_LNG = 111000.0 * math.cos(math.radians(40.78))


def perp_distance_m(p, a, b):
    ax, ay = a[0] * M_PER_DEG_LNG, a[1] * M_PER_DEG_LAT
    bx, by = b[0] * M_PER_DEG_LNG, b[1] * M_PER_DEG_LAT
    px, py = p[0] * M_PER_DEG_LNG, p[1] * M_PER_DEG_LAT
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def rdp(points, epsilon_m):
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
        max_d, max_i = -1.0, -1
        for i in range(i0 + 1, i1):
            d = perp_distance_m(points[i], a, b)
            if d > max_d:
                max_d, max_i = d, i
        if max_d > epsilon_m:
            keep[max_i] = True
            stack.append((i0, max_i))
            stack.append((max_i, i1))
    return [i for i, k in enumerate(keep) if k]


async def snap_one(session, sem, base_url, trip):
    """Replace trip['path'] with OSRM-snapped geometry. On failure, keep original."""
    a = trip["path"][0]
    b = trip["path"][-1]
    url = (f"{base_url}/route/v1/driving/"
           f"{a[0]},{a[1]};{b[0]},{b[1]}"
           "?overview=full&geometries=geojson&steps=false&annotations=false")
    async with sem:
        try:
            async with session.get(url, timeout=30) as r:
                if r.status != 200:
                    return False
                data = await r.json()
                if not data.get("routes"):
                    return False
                coords = data["routes"][0]["geometry"]["coordinates"]
                start_ts = a[2]
                end_ts = b[2]

                # Simplify with DP, then distribute timestamps evenly across kept indices
                simple = rdp(coords, SIMPLIFY_EPSILON_M)
                n = len(simple)
                new_path = []
                for j, idx in enumerate(simple):
                    lng, lat = coords[idx]
                    ts = int(start_ts + (end_ts - start_ts) * j / max(1, n - 1))
                    new_path.append([round(lng, 6), round(lat, 6), ts])
                trip["path"] = new_path
                return True
        except (aiohttp.ClientError, asyncio.TimeoutError):
            return False


async def main_async(args):
    raw_path = Path(args.input)
    out_path = Path(args.output)
    if not raw_path.exists():
        sys.exit(f"Input not found: {raw_path}")

    print(f"Loading {raw_path}...")
    trips = json.loads(raw_path.read_text())
    print(f"  {len(trips):,} trips to snap (concurrency={args.concurrency})")

    sem = asyncio.Semaphore(args.concurrency)
    connector = aiohttp.TCPConnector(limit=args.concurrency * 2)
    timeout = aiohttp.ClientTimeout(total=None, connect=10, sock_read=30)

    started = time.time()
    done = [0]
    ok_count = [0]

    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        async def worker(trip):
            ok = await snap_one(session, sem, args.url, trip)
            done[0] += 1
            if ok:
                ok_count[0] += 1
            if done[0] % max(1, len(trips) // 50) == 0 or done[0] == len(trips):
                elapsed = time.time() - started
                rate = done[0] / max(0.01, elapsed)
                eta = (len(trips) - done[0]) / max(0.01, rate)
                print(f"  {done[0]:>7,}/{len(trips):,}  "
                      f"ok={ok_count[0]:,}  "
                      f"{rate:.0f} trips/sec  "
                      f"eta {eta/60:.1f} min")
        await asyncio.gather(*(worker(t) for t in trips))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(trips, separators=(",", ":")))

    total_pts = sum(len(t["path"]) for t in trips)
    elapsed = time.time() - started
    print(f"\nDone in {elapsed:.0f}s.")
    print(f"  {ok_count[0]:,} snapped, {len(trips) - ok_count[0]:,} kept original")
    print(f"  Total waypoints: {total_pts:,}  (avg {total_pts/len(trips):.1f}/trip)")
    print(f"  -> {out_path}  ({out_path.stat().st_size / 1024 / 1024:.2f} MB)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tier", help="Tier label (25k, 100k, 500k, 2m). "
                                   "Auto-fills --input and --output.")
    ap.add_argument("--input")
    ap.add_argument("--output")
    ap.add_argument("--url", default="http://localhost:5000")
    ap.add_argument("--concurrency", type=int, default=32)
    args = ap.parse_args()

    if args.tier:
        args.input  = args.input  or str(ROOT / "data" / "tiers" / f"trips-{args.tier}.raw.json")
        args.output = args.output or str(ROOT / "data" / "tiers" / f"trips-{args.tier}.json")
    if not args.input or not args.output:
        sys.exit("Provide --tier or both --input and --output")

    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
