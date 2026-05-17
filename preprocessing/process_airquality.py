"""Query the OpenAQ v3 API for NYC PM2.5 stations -> data/airquality.json.

Output schema (matches what index.html expects):
  [
    {
      "id": <openaq_location_id>,
      "name": "...",
      "lat": ..., "lng": ...,
      "hourly_pm25": [24 floats, ug/m3],
      "hourly_intensity": [24 floats in 0..1]
    },
    ...
  ]

Auth:
  Set OPENAQ_API_KEY in the environment. Get a key at https://explore.openaq.org/.

Notes:
  - This script computes a "typical day" by taking the median PM2.5 value per hour
    across the lookback window (default 30 days).
  - 0..1 intensity scales 5 ug/m3 (clean) -> 55 ug/m3 (EPA unhealthy).
"""

import argparse
import json
import os
import statistics
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

BASE_URL = "https://api.openaq.org/v3"
DEFAULT_OUT = Path(__file__).resolve().parent.parent / "data" / "airquality.json"
MANHATTAN_CENTER = (40.7831, -73.9712)


def headers():
    key = os.getenv("OPENAQ_API_KEY")
    if not key:
        print("WARN: OPENAQ_API_KEY not set. OpenAQ v3 may rate-limit unauthenticated requests.",
              file=sys.stderr)
        return {}
    return {"X-API-Key": key}


def find_locations(radius_m: int = 15000, limit: int = 50):
    resp = requests.get(
        f"{BASE_URL}/locations",
        params={
            "coordinates": f"{MANHATTAN_CENTER[0]},{MANHATTAN_CENTER[1]}",
            "radius": radius_m,
            "parameters_id": 2,  # PM2.5
            "limit": limit,
        },
        headers=headers(),
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("results", [])


def fetch_hourly_measurements(location_id: int, days: int = 30):
    """Fetch measurements for the last `days` days and bucket by hour-of-day."""
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)

    bucket = {h: [] for h in range(24)}
    page = 1
    while True:
        resp = requests.get(
            f"{BASE_URL}/locations/{location_id}/measurements",
            params={
                "parameters_id": 2,
                "date_from": start.isoformat(),
                "date_to": end.isoformat(),
                "limit": 1000,
                "page": page,
            },
            headers=headers(),
            timeout=60,
        )
        if resp.status_code == 429:
            time.sleep(2)
            continue
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])
        if not results:
            break
        for m in results:
            ts = m.get("period", {}).get("datetime_from", {}).get("utc") or m.get("date", {}).get("utc")
            value = m.get("value")
            if ts is None or value is None:
                continue
            try:
                hour = datetime.fromisoformat(ts.replace("Z", "+00:00")).hour
                bucket[hour].append(float(value))
            except (ValueError, TypeError):
                continue
        meta = data.get("meta", {})
        if meta.get("found", 0) <= page * 1000:
            break
        page += 1

    profile = []
    for h in range(24):
        vals = bucket[h]
        profile.append(round(statistics.median(vals), 1) if vals else 0.0)
    return profile


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--radius", type=int, default=15000)
    args = ap.parse_args()

    print(f"Finding PM2.5 stations within {args.radius}m of Manhattan...")
    locations = find_locations(radius_m=args.radius)
    print(f"  -> {len(locations)} locations")

    stations = []
    for loc in locations:
        coords = loc.get("coordinates") or {}
        lat, lng = coords.get("latitude"), coords.get("longitude")
        if lat is None or lng is None:
            continue
        print(f"  fetching {loc['id']} ({loc.get('name')})...")
        try:
            profile = fetch_hourly_measurements(loc["id"], days=args.days)
        except requests.HTTPError as e:
            print(f"    skip ({e})")
            continue

        intensity = [round(min(max((v - 5) / 50, 0), 1), 3) for v in profile]
        stations.append({
            "id": loc["id"],
            "name": loc.get("name", f"station-{loc['id']}"),
            "lat": lat,
            "lng": lng,
            "hourly_pm25": profile,
            "hourly_intensity": intensity,
        })

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w") as f:
        json.dump(stations, f, separators=(",", ":"))

    print(f"Wrote {len(stations)} stations -> {out_path}")


if __name__ == "__main__":
    main()
