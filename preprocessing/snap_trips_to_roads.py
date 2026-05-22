"""Snap synthetic taxi trips to the real OpenStreetMap road network using OSRM.

This is an OPTIONAL preprocessing step. The default synthetic generator
(generate_synthetic_data.py) produces trips that route along a model of
Manhattan's grid, which is visually convincing but not pixel-perfect against
the basemap. Running this script replaces each trip's path with the
actual driving route between pickup and dropoff, snapped to real roads
via OSRM's public demo server.

Usage:
    python preprocessing/snap_trips_to_roads.py
    # Pass --max N to only snap the first N trips (useful for testing)
    python preprocessing/snap_trips_to_roads.py --max 50

Notes:
  - The public OSRM server is rate-limited and not guaranteed to be up.
    Failed snaps fall back to the original synthetic path so the file
    is always valid.
  - Snapping 2400 trips takes ~30-60 minutes due to rate limiting.
  - Output overwrites data/trips.json. Back it up first if needed.
"""

import argparse
import json
import sys
import time
from pathlib import Path
from urllib.parse import quote_plus

import requests

OSRM_BASE = "http://router.project-osrm.org/route/v1/driving"
TIMEOUT_SEC = 8
RATE_LIMIT_SLEEP = 0.7   # seconds between requests
RETRY_SLEEP = 5
MAX_RETRIES = 2


def snap(start_lng, start_lat, end_lng, end_lat):
    """Return a list of (lng, lat) waypoints along the snapped route, or None on failure."""
    coords = f"{start_lng},{start_lat};{end_lng},{end_lat}"
    url = f"{OSRM_BASE}/{quote_plus(coords, safe=',;')}"
    params = {"overview": "full", "geometries": "geojson"}

    for attempt in range(MAX_RETRIES + 1):
        try:
            r = requests.get(url, params=params, timeout=TIMEOUT_SEC)
            if r.status_code == 429:
                time.sleep(RETRY_SLEEP * (attempt + 1))
                continue
            r.raise_for_status()
            data = r.json()
            if data.get("code") != "Ok" or not data.get("routes"):
                return None
            return data["routes"][0]["geometry"]["coordinates"]
        except (requests.RequestException, ValueError):
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_SLEEP)
            else:
                return None
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="data/trips.json")
    ap.add_argument("--output", default="data/trips.json")
    ap.add_argument("--max", type=int, default=0,
                    help="If >0, snap only the first N trips (rest passed through unchanged).")
    args = ap.parse_args()

    in_path = Path(args.input)
    if not in_path.exists():
        sys.exit(f"Input not found: {in_path}")

    with in_path.open() as f:
        trips = json.load(f)

    limit = args.max if args.max > 0 else len(trips)
    print(f"Snapping {min(limit, len(trips))} of {len(trips)} trips against OSRM…")
    print("Estimated time: " + f"{min(limit, len(trips)) * RATE_LIMIT_SLEEP / 60:.1f} minutes")

    ok = 0
    failed = 0
    for i, trip in enumerate(trips[:limit]):
        path = trip["path"]
        if len(path) < 2:
            continue
        start_lng, start_lat = path[0][0], path[0][1]
        end_lng, end_lat = path[-1][0], path[-1][1]
        start_ts = path[0][2]
        end_ts = path[-1][2]

        coords = snap(start_lng, start_lat, end_lng, end_lat)
        if coords and len(coords) >= 2:
            n = len(coords)
            new_path = [
                [round(c[0], 6), round(c[1], 6),
                 int(start_ts + (end_ts - start_ts) * j / (n - 1))]
                for j, c in enumerate(coords)
            ]
            trip["path"] = new_path
            ok += 1
        else:
            failed += 1

        if (i + 1) % 25 == 0:
            print(f"  {i + 1}/{limit}  ok={ok}  failed={failed}")

        time.sleep(RATE_LIMIT_SLEEP)

    out_path = Path(args.output)
    out_path.write_text(json.dumps(trips, separators=(",", ":")))
    print(f"\nDone. {ok} snapped, {failed} fallback (kept synthetic path). "
          f"Wrote {out_path} ({out_path.stat().st_size / 1024:.1f} KB).")


if __name__ == "__main__":
    main()
