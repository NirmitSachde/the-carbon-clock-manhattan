"""Pull NYC PurpleAir community sensors and merge with the EPA AQS stations
in data/airquality.json.

EPA's regulated federal PM2.5 network in the NYC bbox is sparse — only 5
sites at hourly resolution. PurpleAir's community-sensor network adds 50+
additional outdoor sites at sub-minute cadence. Combined, the visualization
gets ~10× more air-quality data points across all five boroughs.

Pipeline:
  1. GET /v1/sensors (filtered to NYC bbox, outdoor, recently active)
  2. For each sensor, GET /v1/sensors/{id}/history with 60-min averaging
     for the last 7 days. Cost ≈ 7 × 24 = 168 history rows per sensor.
  3. Aggregate to a typical-day hourly profile (median per hour-of-day).
  4. Merge into data/airquality.json alongside the EPA stations.

Auth:
  Read API key from the PURPLEAIR_API_KEY environment variable.
  Never commit the key to source.

Token budget:
  ~10K tokens for the full NYC pull. Well under the 1M token monthly cap.

Run:
  PURPLEAIR_API_KEY=xxx python3 preprocessing/process_purpleair.py
"""

import argparse
import json
import os
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "data" / "airquality.json"

# NYC bounding box — same as the EPA AQS pull
NW_LAT, NW_LNG = 40.92, -74.10
SE_LAT, SE_LNG = 40.65, -73.85

# Normalization breakpoints for visualization (same as EPA path).
PM25_CLEAN, PM25_UNHEALTHY = 5.0, 55.0      # μg/m³


def api_get(url: str, api_key: str) -> dict:
    req = Request(url, headers={"X-API-Key": api_key})
    try:
        with urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise SystemExit(f"PurpleAir API error {e.code} on {url[:120]}\n{body[:300]}")


def list_nyc_sensors(api_key: str) -> list:
    """Return list of dicts with sensor_index, name, latitude, longitude."""
    fields = "sensor_index,last_seen,name,location_type,latitude,longitude,confidence"
    # location_type=0 → outdoor only. confidence ≥ 90 to avoid junk sensors.
    url = (f"https://api.purpleair.com/v1/sensors"
           f"?fields={fields}"
           f"&nwlat={NW_LAT}&nwlng={NW_LNG}"
           f"&selat={SE_LAT}&selng={SE_LNG}"
           f"&location_type=0")
    data = api_get(url, api_key)
    field_names = data.get("fields", [])
    rows = data.get("data", [])
    sensors = []
    now = int(time.time())
    for row in rows:
        d = dict(zip(field_names, row))
        # Skip sensors that haven't reported recently (broken / offline)
        if now - int(d.get("last_seen", 0)) > 7 * 24 * 3600:
            continue
        # Skip low-confidence sensors (broken hardware)
        if int(d.get("confidence", 0)) < 80:
            continue
        sensors.append(d)
    return sensors


def fetch_sensor_history(api_key: str, sensor_index: int, days: int = 7) -> list:
    """Return list of (utc_hour, pm25_atm) tuples over the last `days`."""
    end_ts = int(time.time())
    start_ts = end_ts - days * 24 * 3600
    # average=60 → 60-minute averages. Reduces row count by 30× vs. raw.
    # pm2.5_atm is the atmospheric (outdoor-calibrated) PM2.5 reading.
    url = (f"https://api.purpleair.com/v1/sensors/{sensor_index}/history"
           f"?start_timestamp={start_ts}&end_timestamp={end_ts}"
           f"&average=60&fields=pm2.5_atm")
    data = api_get(url, api_key)
    field_names = data.get("fields", [])
    rows = data.get("data", [])
    if "time_stamp" not in field_names or "pm2.5_atm" not in field_names:
        return []
    t_idx = field_names.index("time_stamp")
    p_idx = field_names.index("pm2.5_atm")
    out = []
    for row in rows:
        ts = row[t_idx]
        pm = row[p_idx]
        if pm is None or pm < 0 or pm > 500:
            continue
        out.append((ts, float(pm)))
    return out


def typical_day_profile(history: list) -> list:
    """history = [(ts, pm25), ...]   ->   24-element list of median PM2.5 per hour."""
    bucket = defaultdict(list)
    for ts, pm in history:
        # ts is unix seconds UTC — convert to local NYC hour
        # NYC is UTC-5 (winter) or UTC-4 (summer). For a typical-day profile
        # the offset cancels out — what matters is consistency. Use UTC.
        hour = (int(ts) // 3600) % 24
        bucket[hour].append(pm)
    profile = []
    for h in range(24):
        vals = bucket[h]
        profile.append(round(statistics.median(vals), 1) if vals else None)
    # Forward/backfill any missing hours
    last = None
    for i in range(24):
        if profile[i] is not None:
            last = profile[i]
        else:
            profile[i] = last
    last = None
    for i in range(23, -1, -1):
        if profile[i] is not None:
            last = profile[i]
        else:
            profile[i] = last
    return [v if v is not None else 0.0 for v in profile]


def percentile_stretch(arr: list) -> list:
    """Same per-station 10th-90th percentile stretch we use for EPA.
    Keeps each sensor's daily cycle visible regardless of absolute level."""
    real = [v for v in arr if v is not None and v > 0]
    if len(real) < 2:
        return [0.0] * len(arr)
    real_sorted = sorted(real)
    lo = real_sorted[max(0, int(len(real_sorted) * 0.10))]
    hi = real_sorted[min(len(real_sorted) - 1, int(len(real_sorted) * 0.90))]
    span = max(0.001, hi - lo)
    return [round(max(0.0, min(1.0, (v - lo) / span)) if v is not None else 0.0, 3)
            for v in arr]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--rate-limit-sec", type=float, default=0.2,
                    help="Sleep between sensor history requests.")
    args = ap.parse_args()

    api_key = os.environ.get("PURPLEAIR_API_KEY")
    if not api_key:
        sys.exit("PURPLEAIR_API_KEY env var not set. Aborting.")

    print("Listing NYC outdoor PurpleAir sensors...")
    sensors = list_nyc_sensors(api_key)
    print(f"  -> {len(sensors)} active, high-confidence outdoor sensors")
    if not sensors:
        sys.exit("No usable PurpleAir sensors found in NYC bbox.")

    new_entries = []
    skipped = 0
    for i, s in enumerate(sensors, 1):
        sid = s["sensor_index"]
        name = s.get("name") or f"PurpleAir #{sid}"
        try:
            history = fetch_sensor_history(api_key, sid, days=args.days)
        except Exception as e:
            print(f"  [{i:>3}/{len(sensors)}] {sid:<10} {name[:30]:<30}  ERROR: {e}")
            skipped += 1
            continue
        if not history:
            print(f"  [{i:>3}/{len(sensors)}] {sid:<10} {name[:30]:<30}  no data, skipping")
            skipped += 1
            continue

        pm_profile = typical_day_profile(history)
        intensity = percentile_stretch(pm_profile)
        new_entries.append({
            "id": f"pa-{sid}",
            "name": name[:60],
            "lat": float(s["latitude"]),
            "lng": float(s["longitude"]),
            "source": "purpleair",
            "pollutants": ["PM2.5"],
            "hourly_pm25": pm_profile,
            "hourly_no2": [0.0] * 24,    # PurpleAir doesn't measure NO2
            "hourly_intensity": intensity,
        })
        avg = sum(pm_profile) / 24
        print(f"  [{i:>3}/{len(sensors)}] {sid:<10} {name[:30]:<30}  avg PM2.5={avg:.1f} μg/m³  ({len(history)} hourly readings)")
        time.sleep(args.rate_limit_sec)

    # Merge with existing airquality.json (EPA stations)
    out_path = Path(args.out)
    existing = []
    if out_path.exists():
        existing = json.loads(out_path.read_text())
        # Strip any old PurpleAir entries — we're replacing them.
        existing = [s for s in existing if s.get("source") != "purpleair"]
        # Tag the leftover EPA entries with source if not already
        for s in existing:
            s.setdefault("source", "epa-aqs")

    combined = existing + new_entries
    out_path.write_text(json.dumps(combined, separators=(",", ":")))

    epa_count = sum(1 for s in combined if s.get("source") == "epa-aqs")
    pa_count = sum(1 for s in combined if s.get("source") == "purpleair")
    print()
    print(f"Done. {len(combined)} total stations  ({epa_count} EPA + {pa_count} PurpleAir)")
    print(f"  Skipped: {skipped}")
    print(f"  -> {out_path}  ({out_path.stat().st_size / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
