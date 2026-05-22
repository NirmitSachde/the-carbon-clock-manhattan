"""Process EPA AQS hourly PM2.5 data into airquality.json.

Source: https://aqs.epa.gov/aqsweb/airdata/hourly_88101_YYYY.zip
The 2025 CSV is ~1.4 GB once unzipped, so we read it in chunks and only
keep rows from the NYC metro area, then aggregate each station's typical-
day hourly profile.

Output schema (matches what index.html expects):
  [{ id, name, lat, lng, hourly_pm25: [24 floats ug/m3], hourly_intensity: [24 floats in 0..1] }, ...]
"""

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CSV = ROOT / "raw" / "hourly_88101_2025.csv"
DEFAULT_OUT = ROOT / "data" / "airquality.json"

# NYC bounding box (Manhattan + close neighbors that influence Manhattan air)
LAT_MIN, LAT_MAX = 40.65, 40.92
LNG_MIN, LNG_MAX = -74.10, -73.85


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=str(DEFAULT_CSV))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--chunksize", type=int, default=500_000)
    args = ap.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.exists():
        sys.exit(f"AQS CSV not found: {csv_path}")

    keep_cols = [
        "State Code", "County Code", "Site Num",
        "Latitude", "Longitude",
        "Date Local", "Time Local",
        "Sample Measurement",
        "County Name", "State Name",
    ]
    # State 36 = New York
    print(f"Streaming {csv_path} in {args.chunksize:,}-row chunks...")
    pieces = []
    total_rows = 0
    for chunk in pd.read_csv(csv_path, chunksize=args.chunksize,
                             usecols=lambda c: c in keep_cols,
                             low_memory=False, dtype={"State Code": str, "County Code": str, "Site Num": str}):
        total_rows += len(chunk)
        # Filter to NY state then to NYC bounding box
        chunk = chunk[chunk["State Code"] == "36"]
        if len(chunk) == 0:
            continue
        chunk = chunk[
            (chunk["Latitude"] >= LAT_MIN) & (chunk["Latitude"] <= LAT_MAX) &
            (chunk["Longitude"] >= LNG_MIN) & (chunk["Longitude"] <= LNG_MAX)
        ]
        if len(chunk) == 0:
            continue
        pieces.append(chunk)
        print(f"  scanned {total_rows:,}, kept {sum(len(p) for p in pieces):,} so far")

    if not pieces:
        sys.exit("No NYC-area readings found in the AQS file.")

    df = pd.concat(pieces, ignore_index=True)
    print(f"\nTotal NYC PM2.5 readings: {len(df):,}")

    # Site key: state + county + site num. Combine into a unique id.
    df["site_id"] = (df["State Code"].astype(str) + "-"
                     + df["County Code"].astype(str) + "-"
                     + df["Site Num"].astype(str))

    # Hour-of-day from "HH:MM" Time Local
    df["hour"] = df["Time Local"].astype(str).str.slice(0, 2).astype(int) % 24

    # Drop NaN measurements and clip to a sane range
    df = df.dropna(subset=["Sample Measurement"])
    df = df[(df["Sample Measurement"] >= 0) & (df["Sample Measurement"] <= 500)]
    print(f"After filtering: {len(df):,} valid readings, {df['site_id'].nunique()} sites")

    # Per-site median per hour-of-day = typical-day profile
    print("Computing typical-day hourly profiles per site...")
    grp = df.groupby(["site_id", "hour"])["Sample Measurement"].median().reset_index()
    pivot = grp.pivot(index="site_id", columns="hour", values="Sample Measurement").fillna(method="ffill", axis=1).fillna(method="bfill", axis=1)

    # Site metadata: pick one representative row per site (lat/lng/name)
    meta = df.groupby("site_id").agg(
        Latitude=("Latitude", "first"),
        Longitude=("Longitude", "first"),
        County=("County Name", "first"),
    ).reset_index()

    out = []
    for i, row in enumerate(meta.itertuples(index=False)):
        sid = row.site_id
        if sid not in pivot.index:
            continue
        hourly = pivot.loc[sid].reindex(range(24)).fillna(method="ffill").fillna(method="bfill").tolist()
        if any(pd.isna(v) for v in hourly):
            continue
        hourly_pm = [round(float(v), 1) for v in hourly]
        intensity = [round(min(max((v - 5) / 50, 0), 1), 3) for v in hourly_pm]

        county = row.County or ""
        name = f"{county} {sid}".strip() or "PM2.5 monitor"
        out.append({
            "id": i + 1,
            "name": name[:60],
            "lat": float(row.Latitude),
            "lng": float(row.Longitude),
            "hourly_pm25": hourly_pm,
            "hourly_intensity": intensity,
        })

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w") as f:
        json.dump(out, f, separators=(",", ":"))

    print(f"\nWrote {len(out)} PM2.5 stations -> {out_path}")
    print(f"File size: {out_path.stat().st_size / 1024:.1f} KB")
    for s in out[:5]:
        print(f"  {s['id']:>2} {s['name'][:30]:<30} ({s['lat']}, {s['lng']}) "
              f"daily avg={sum(s['hourly_pm25'])/24:.1f} μg/m³")


if __name__ == "__main__":
    main()
