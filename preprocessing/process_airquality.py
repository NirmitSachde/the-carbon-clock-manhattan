"""Process EPA AQS hourly air-quality data into airquality.json.

Combines two regulated criteria pollutants:
  - PM2.5 (parameter code 88101) — fine particulate matter, μg/m³
  - NO2  (parameter code 42602) — nitrogen dioxide, ppb (strong indicator
    of vehicle/combustion sources, complements PM2.5 in urban air)

Each AQS monitoring site becomes one entry in airquality.json. Sites may
publish either pollutant or both. Intensity is the max of the per-
pollutant normalized intensities, so a station with high NO2 or high PM2.5
both show as 'unhealthy'.

Source files (download manually before running):
  https://aqs.epa.gov/aqsweb/airdata/hourly_88101_2025.zip
  https://aqs.epa.gov/aqsweb/airdata/hourly_42602_2025.zip
"""

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent

# NYC metropolitan bounding box — Manhattan plus near neighbors that
# contribute to its air column.
LAT_MIN, LAT_MAX = 40.65, 40.92
LNG_MIN, LNG_MAX = -74.10, -73.85

# Normalization breakpoints. Below `clean` -> intensity 0. Above `unhealthy` -> 1.
PM25_CLEAN, PM25_UNHEALTHY = 5.0, 55.0    # μg/m³ — WHO + US EPA AQI
NO2_CLEAN, NO2_UNHEALTHY = 5.0, 50.0      # ppb — typical urban background to elevated

KEEP_COLS = [
    "State Code", "County Code", "Site Num",
    "Latitude", "Longitude",
    "Time Local",
    "Sample Measurement",
    "County Name",
]


def normalize(v, lo, hi):
    if pd.isna(v):
        return 0.0
    return float(max(0.0, min(1.0, (v - lo) / (hi - lo))))


def aggregate(csv_path: Path, label: str, chunksize: int = 500_000) -> pd.DataFrame:
    """Stream a (huge) AQS CSV, filter to NYC bbox, aggregate hourly per-site median."""
    if not csv_path.exists():
        print(f"  {label}: file missing ({csv_path}) — skipping this pollutant.")
        return None

    pieces = []
    scanned = 0
    for chunk in pd.read_csv(csv_path, chunksize=chunksize,
                             usecols=lambda c: c in KEEP_COLS,
                             low_memory=False,
                             dtype={"State Code": str, "County Code": str, "Site Num": str}):
        scanned += len(chunk)
        chunk = chunk[chunk["State Code"] == "36"]
        if chunk.empty:
            continue
        chunk = chunk[
            (chunk["Latitude"] >= LAT_MIN) & (chunk["Latitude"] <= LAT_MAX) &
            (chunk["Longitude"] >= LNG_MIN) & (chunk["Longitude"] <= LNG_MAX)
        ]
        if chunk.empty:
            continue
        pieces.append(chunk)

    if not pieces:
        print(f"  {label}: no NYC-area readings found.")
        return None

    df = pd.concat(pieces, ignore_index=True)
    df = df.dropna(subset=["Sample Measurement"])
    df["site_id"] = (df["State Code"].astype(str) + "-"
                     + df["County Code"].astype(str) + "-"
                     + df["Site Num"].astype(str))
    df["hour"] = df["Time Local"].astype(str).str.slice(0, 2).astype(int) % 24
    # Drop obviously bad measurements
    df = df[df["Sample Measurement"] >= 0]

    sites = df["site_id"].nunique()
    print(f"  {label}: scanned {scanned:,} rows, kept {len(df):,} readings across {sites} NYC sites")

    grp = df.groupby(["site_id", "hour"])["Sample Measurement"].median().reset_index()
    pivot = grp.pivot(index="site_id", columns="hour", values="Sample Measurement")
    pivot = pivot.ffill(axis=1).bfill(axis=1)

    meta = df.groupby("site_id").agg(
        Latitude=("Latitude", "first"),
        Longitude=("Longitude", "first"),
        County=("County Name", "first"),
    ).reset_index().set_index("site_id")

    pivot = pivot.join(meta, how="left")
    return pivot


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pm25-csv", default=str(ROOT / "raw" / "hourly_88101_2025.csv"))
    ap.add_argument("--no2-csv",  default=str(ROOT / "raw" / "hourly_42602_2025.csv"))
    ap.add_argument("--out",      default=str(ROOT / "data" / "airquality.json"))
    args = ap.parse_args()

    print("Processing PM2.5 (88101)...")
    pm = aggregate(Path(args.pm25_csv), "PM2.5")
    print("Processing NO2 (42602)...")
    no2 = aggregate(Path(args.no2_csv), "NO2")

    if pm is None and no2 is None:
        sys.exit("No AQS data available for either pollutant. Download the AQS zips first.")

    # Collect all unique site IDs across both pollutants
    all_sites = set()
    if pm is not None: all_sites.update(pm.index)
    if no2 is not None: all_sites.update(no2.index)

    out = []
    for sid in sorted(all_sites):
        pm_row = pm.loc[sid] if pm is not None and sid in pm.index else None
        no2_row = no2.loc[sid] if no2 is not None and sid in no2.index else None

        # Use whichever pollutant carries the site metadata
        anchor = pm_row if pm_row is not None else no2_row
        lat = float(anchor["Latitude"])
        lng = float(anchor["Longitude"])
        county = str(anchor.get("County") or "")

        pm_hourly = [None] * 24
        no2_hourly = [None] * 24
        if pm_row is not None:
            for h in range(24):
                if h in pm_row.index:
                    v = pm_row[h]
                    if pd.notna(v): pm_hourly[h] = round(float(v), 1)
        if no2_row is not None:
            for h in range(24):
                if h in no2_row.index:
                    v = no2_row[h]
                    if pd.notna(v): no2_hourly[h] = round(float(v), 1)

        # Combined intensity per hour: max of normalized PM2.5 and normalized NO2
        intensity = []
        for h in range(24):
            i_pm = normalize(pm_hourly[h], PM25_CLEAN, PM25_UNHEALTHY) if pm_hourly[h] is not None else 0.0
            i_no2 = normalize(no2_hourly[h], NO2_CLEAN, NO2_UNHEALTHY) if no2_hourly[h] is not None else 0.0
            intensity.append(round(max(i_pm, i_no2), 3))

        # Fill in any missing hourly values via forward/backfill (keep file shape consistent)
        def ffill_list(arr):
            last = None
            for i in range(24):
                if arr[i] is not None: last = arr[i]
                else: arr[i] = last
            last = None
            for i in range(23, -1, -1):
                if arr[i] is not None: last = arr[i]
                else: arr[i] = last
            return [v if v is not None else 0.0 for v in arr]

        pm_hourly = ffill_list(pm_hourly)
        no2_hourly = ffill_list(no2_hourly)

        pollutants = []
        if pm_row is not None: pollutants.append("PM2.5")
        if no2_row is not None: pollutants.append("NO2")

        out.append({
            "id": sid,
            "name": f"{county} · {sid}".strip(" ·"),
            "lat": lat,
            "lng": lng,
            "pollutants": pollutants,
            "hourly_pm25": pm_hourly,
            "hourly_no2": no2_hourly,
            "hourly_intensity": intensity,
        })

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, separators=(",", ":")))

    print(f"\nWrote {len(out)} monitoring sites -> {out_path}")
    print(f"File size: {out_path.stat().st_size / 1024:.1f} KB")
    for s in out:
        pm_avg = sum(s["hourly_pm25"]) / 24 if any(s["hourly_pm25"]) else 0
        no2_avg = sum(s["hourly_no2"]) / 24 if any(s["hourly_no2"]) else 0
        print(f"  {s['id']}  ({s['lat']}, {s['lng']})  "
              f"{','.join(s['pollutants']):<11}  "
              f"PM2.5 avg={pm_avg:.1f}  NO2 avg={no2_avg:.1f}")


if __name__ == "__main__":
    main()
