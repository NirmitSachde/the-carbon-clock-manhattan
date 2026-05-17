"""Process NYC TLC yellow taxi Parquet -> data/trips.json.

Pipeline:
  1. Read one month of yellow taxi trip records (Parquet).
  2. Filter to Manhattan-only PU/DO zones.
  3. Stratified sample ~100K trips, balanced across the 24h day.
  4. Join taxi zone IDs to centroid coordinates.
  5. Interpolate each trip into ~10 waypoints (lng, lat, sec_since_midnight).
  6. Tag each trip with a 0-1 color_intensity proxy (trip distance).
  7. Write data/trips.json.

Required inputs alongside this script:
  - yellow_tripdata_YYYY-MM.parquet      (TLC monthly trip records)
  - zone_centroids.csv                   (columns: zone_id, lat, lng)

zone_centroids.csv can be built from the TLC taxi zone shapefile:
  https://data.cityofnewyork.us/Transportation/NYC-Taxi-Zones/d3c1-ddgc
"""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

# Manhattan taxi zone IDs (per TLC taxi zone lookup).
MANHATTAN_ZONES = [
    4, 12, 13, 24, 41, 42, 43, 45, 48, 50, 68, 74, 75, 79, 87, 88, 90, 100,
    103, 104, 105, 107, 113, 114, 116, 120, 125, 127, 128, 137, 140, 141, 142,
    143, 144, 148, 151, 152, 153, 158, 161, 162, 163, 164, 166, 170, 186, 194,
    202, 209, 211, 224, 229, 230, 231, 232, 233, 234, 236, 237, 238, 239, 243,
    244, 246, 249, 261, 262, 263,
]

DEFAULT_PARQUET = "yellow_tripdata_2025-01.parquet"
DEFAULT_CENTROIDS = "zone_centroids.csv"
DEFAULT_OUT = Path(__file__).resolve().parent.parent / "data" / "trips.json"
DEFAULT_SAMPLE_PER_HOUR = 4200  # ~100K total trips


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--parquet", default=DEFAULT_PARQUET)
    ap.add_argument("--centroids", default=DEFAULT_CENTROIDS)
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--per-hour", type=int, default=DEFAULT_SAMPLE_PER_HOUR)
    ap.add_argument("--n-waypoints", type=int, default=10)
    args = ap.parse_args()

    print(f"Reading {args.parquet}...")
    df = pd.read_parquet(args.parquet)

    print(f"Filtering to Manhattan zones...")
    df = df[
        df["PULocationID"].isin(MANHATTAN_ZONES)
        & df["DOLocationID"].isin(MANHATTAN_ZONES)
    ].copy()

    df["hour"] = df["tpep_pickup_datetime"].dt.hour
    print(f"  -> {len(df):,} Manhattan trips")

    print(f"Sampling {args.per_hour:,} trips per hour (stratified)...")
    sampled = (
        df.groupby("hour", group_keys=False)
        .apply(lambda x: x.sample(min(len(x), args.per_hour), random_state=42))
        .reset_index(drop=True)
    )
    print(f"  -> {len(sampled):,} trips after sampling")

    print(f"Joining zone centroids from {args.centroids}...")
    zones = pd.read_csv(args.centroids)
    zones.columns = [c.lower() for c in zones.columns]
    if not {"zone_id", "lat", "lng"}.issubset(zones.columns):
        raise SystemExit(
            f"{args.centroids} must have columns: zone_id, lat, lng (got {list(zones.columns)})"
        )

    sampled = sampled.merge(
        zones[["zone_id", "lat", "lng"]],
        left_on="PULocationID", right_on="zone_id", how="inner",
    ).rename(columns={"lat": "pu_lat", "lng": "pu_lng"}).drop(columns=["zone_id"])

    sampled = sampled.merge(
        zones[["zone_id", "lat", "lng"]],
        left_on="DOLocationID", right_on="zone_id", how="inner",
    ).rename(columns={"lat": "do_lat", "lng": "do_lng"}).drop(columns=["zone_id"])

    print(f"  -> {len(sampled):,} trips after zone join")

    print("Building trip paths...")
    trips = []
    n_points = args.n_waypoints
    for row in sampled.itertuples(index=False):
        start_sec = (
            row.tpep_pickup_datetime.hour * 3600
            + row.tpep_pickup_datetime.minute * 60
            + row.tpep_pickup_datetime.second
        )
        end_sec = (
            row.tpep_dropoff_datetime.hour * 3600
            + row.tpep_dropoff_datetime.minute * 60
            + row.tpep_dropoff_datetime.second
        )
        if end_sec <= start_sec:
            end_sec = start_sec + 600  # fallback 10 min

        ts = np.linspace(start_sec, end_sec, n_points)
        lngs = np.linspace(row.pu_lng, row.do_lng, n_points)
        lats = np.linspace(row.pu_lat, row.do_lat, n_points)

        path = [
            [round(float(lng), 6), round(float(lat), 6), int(t)]
            for lng, lat, t in zip(lngs, lats, ts)
        ]

        distance = getattr(row, "trip_distance", 2.0) or 2.0
        color_intensity = round(min(float(distance) / 10.0, 1.0), 2)

        trips.append({"path": path, "color_intensity": color_intensity})

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w") as f:
        json.dump(trips, f, separators=(",", ":"))

    print(f"Wrote {len(trips):,} trips -> {out_path} "
          f"({out_path.stat().st_size / 1024 / 1024:.2f} MB)")


if __name__ == "__main__":
    main()
