"""Build multiple trip-sample sizes from the same TLC parquet.

Produces tier-keyed JSON files in data/tiers/ ready to be road-snapped:
  data/tiers/trips-25k.raw.json
  data/tiers/trips-100k.raw.json
  data/tiers/trips-500k.raw.json
  data/tiers/trips-2m.raw.json    (everything, stratified)

Each file has the same schema as the existing trips.json: a list of
  {"path": [[lng, lat, sec], ...], "color_intensity": 0..1}

Run:
    python3 preprocessing/build_trip_tiers.py
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent

# Same Manhattan zone IDs as process_taxi.py
MANHATTAN_ZONES = [
    4, 12, 13, 24, 41, 42, 43, 45, 48, 50, 68, 74, 75, 79, 87, 88, 90, 100,
    103, 104, 105, 107, 113, 114, 116, 120, 125, 127, 128, 137, 140, 141, 142,
    143, 144, 148, 151, 152, 153, 158, 161, 162, 163, 164, 166, 170, 186, 194,
    202, 209, 211, 224, 229, 230, 231, 232, 233, 234, 236, 237, 238, 239, 243,
    244, 246, 249, 261, 262, 263,
]

# Tier definitions: (label, per-hour cap). per-hour cap × 24 ≈ total.
# Last tier uses None → keep everything.
TIERS = [
    ("25k",  1042),    # ~25,000
    ("100k", 4167),    # ~100,000
    ("500k", 20834),   # ~500,000
    ("2m",   None),    # all Manhattan trips
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--parquet", default=str(ROOT / "raw" / "yellow_tripdata_2025-01.parquet"))
    ap.add_argument("--centroids", default=str(ROOT / "raw" / "zone_centroids.csv"))
    ap.add_argument("--out-dir", default=str(ROOT / "data" / "tiers"))
    args = ap.parse_args()

    parquet = Path(args.parquet)
    if not parquet.exists():
        sys.exit(f"Parquet not found: {parquet}. Run downloads first.")

    print(f"Reading {parquet}...")
    df = pd.read_parquet(parquet)
    print(f"  -> {len(df):,} total Jan-2025 trips")

    df = df[
        df["PULocationID"].isin(MANHATTAN_ZONES)
        & df["DOLocationID"].isin(MANHATTAN_ZONES)
    ].copy()
    df["hour"] = df["tpep_pickup_datetime"].dt.hour
    print(f"  -> {len(df):,} Manhattan PU+DO trips")

    print(f"Joining zone centroids from {args.centroids}...")
    zones = pd.read_csv(args.centroids)
    zones.columns = [c.lower() for c in zones.columns]

    df = df.merge(
        zones[["zone_id", "lat", "lng"]],
        left_on="PULocationID", right_on="zone_id", how="inner",
    ).rename(columns={"lat": "pu_lat", "lng": "pu_lng"}).drop(columns=["zone_id"])
    df = df.merge(
        zones[["zone_id", "lat", "lng"]],
        left_on="DOLocationID", right_on="zone_id", how="inner",
    ).rename(columns={"lat": "do_lat", "lng": "do_lng"}).drop(columns=["zone_id"])
    print(f"  -> {len(df):,} after zone-centroid join")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    for label, per_hour in TIERS:
        print(f"\n=== Tier {label} ===")
        if per_hour is None:
            sampled = df
        else:
            sampled = (
                df.groupby("hour", group_keys=False)
                .apply(lambda x: x.sample(min(len(x), per_hour), random_state=42))
                .reset_index(drop=True)
            )
        print(f"  {len(sampled):,} trips after stratified sample")

        out_trips = []
        for row in sampled.itertuples(index=False):
            start = (row.tpep_pickup_datetime.hour * 3600
                     + row.tpep_pickup_datetime.minute * 60
                     + row.tpep_pickup_datetime.second)
            end = (row.tpep_dropoff_datetime.hour * 3600
                   + row.tpep_dropoff_datetime.minute * 60
                   + row.tpep_dropoff_datetime.second)
            if end <= start:
                end = start + 600

            # Two-point straight-line "raw" path. OSRM will replace this with
            # full road geometry. We just keep the endpoints + timestamps.
            path = [
                [round(float(row.pu_lng), 6), round(float(row.pu_lat), 6), int(start)],
                [round(float(row.do_lng), 6), round(float(row.do_lat), 6), int(end)],
            ]
            distance = float(getattr(row, "trip_distance", 2.0) or 2.0)
            color_intensity = round(min(distance / 10.0, 1.0), 2)
            out_trips.append({"path": path, "color_intensity": color_intensity})

        out_file = out_dir / f"trips-{label}.raw.json"
        out_file.write_text(json.dumps(out_trips, separators=(",", ":")))
        size_kb = out_file.stat().st_size / 1024
        print(f"  Wrote {out_file.name} ({size_kb:,.0f} KB)")


if __name__ == "__main__":
    main()
