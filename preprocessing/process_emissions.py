"""Process the real NYC DOT Automated Traffic Volume Counts CSV.

Adapted to the actual published format:
  RequestID, Boro, Yr, M, D, HH, MM, Vol, SegmentID, WktGeom, street, fromSt, toSt, Direction

The WktGeom is a POINT in EPSG:2263 (NY State Plane / NAD83) — we reproject
to WGS84 lat/lng. Volumes are aggregated by (lat, lng, hour) across all
recent Manhattan counts, then converted to a 0-1 intensity using EPA fleet-
mix emission factors.

Run:
    python3 preprocessing/process_emissions_real.py
"""

import argparse
import json
import re
import sys
from pathlib import Path

import pandas as pd
from pyproj import Transformer

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CSV = ROOT / "raw" / "traffic_counts.csv"
DEFAULT_OUT = ROOT / "data" / "emissions.json"

# EPA emission factors (g CO2 / vehicle mile)
EMISSION_FACTORS = {"car": 400, "light_truck": 540, "heavy_truck": 1600, "bus": 2200}
FLEET_MIX = {"car": 0.75, "light_truck": 0.15, "heavy_truck": 0.08, "bus": 0.02}
AVG_FACTOR = sum(FLEET_MIX[k] * EMISSION_FACTORS[k] for k in FLEET_MIX)
AVG_TRIP_MILES = 2.0    # rough miles past each count station

WKT_POINT_RE = re.compile(r"POINT \(([-\d.]+)\s+([-\d.]+)\)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=str(DEFAULT_CSV))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--manhattan-only", action="store_true", default=True)
    ap.add_argument("--min-year", type=int, default=2020,
                    help="Only use counts from this year onward.")
    args = ap.parse_args()

    print(f"Reading {args.csv} (this is ~13 MB — should be quick)...")
    df = pd.read_csv(args.csv)
    print(f"  -> {len(df):,} count records total")

    # Filter to Manhattan and recent years for relevance.
    if args.manhattan_only:
        df = df[df["Boro"].astype(str).str.strip() == "Manhattan"]
        print(f"  -> {len(df):,} after Manhattan filter")
    if "Yr" in df.columns:
        df = df[df["Yr"] >= args.min_year]
        print(f"  -> {len(df):,} after year >= {args.min_year}")

    if len(df) == 0:
        sys.exit("No rows left after filtering — try a lower --min-year")

    # Parse WktGeom into NY State Plane (x, y)
    print("Parsing WKT geometry...")
    parsed = df["WktGeom"].astype(str).str.extract(WKT_POINT_RE)
    df["sp_x"] = pd.to_numeric(parsed[0], errors="coerce")
    df["sp_y"] = pd.to_numeric(parsed[1], errors="coerce")
    df = df.dropna(subset=["sp_x", "sp_y"])

    # Reproject EPSG:2263 -> WGS84
    print("Reprojecting to WGS84...")
    transformer = Transformer.from_crs("EPSG:2263", "EPSG:4326", always_xy=True)
    lngs, lats = transformer.transform(df["sp_x"].values, df["sp_y"].values)
    df["lng"] = lngs
    df["lat"] = lats

    # Round positions a bit so we collapse repeated measurements at the same station
    df["lat_b"] = df["lat"].round(4)
    df["lng_b"] = df["lng"].round(4)
    df["HH"] = df["HH"].astype(int) % 24

    print(f"  -> {df.groupby(['lat_b', 'lng_b']).ngroups} unique stations")

    # Aggregate volume per (station, hour)
    print("Aggregating by (station, hour)...")
    hourly = (
        df.groupby(["lat_b", "lng_b", "HH"])["Vol"]
        .mean()
        .reset_index()
        .rename(columns={"lat_b": "lat", "lng_b": "lng"})
    )
    hourly["emissions_g"] = hourly["Vol"] * AVG_FACTOR * AVG_TRIP_MILES
    max_em = hourly["emissions_g"].max()
    if not max_em or pd.isna(max_em):
        sys.exit("No volume data — cannot normalize")
    hourly["intensity"] = (hourly["emissions_g"] / max_em).round(3)

    # Build 24 hourly snapshots
    result = {}
    for hour in range(24):
        snap = hourly[hourly["HH"] == hour]
        result[str(hour)] = [
            {"lng": float(r.lng), "lat": float(r.lat), "intensity": float(r.intensity)}
            for r in snap.itertuples(index=False)
        ]

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w") as f:
        json.dump(result, f, separators=(",", ":"))

    total = sum(len(v) for v in result.values())
    print(f"\nWrote {total:,} (station, hour) points -> {out_path}")
    print(f"File size: {out_path.stat().st_size / 1024:.1f} KB")
    # Sanity summary
    for h in [3, 8, 18]:
        arr = result[str(h)]
        if arr:
            intensities = [p["intensity"] for p in arr]
            print(f"  hour {h:02d}: {len(arr)} stations, "
                  f"mean={sum(intensities)/len(intensities):.3f} "
                  f"max={max(intensities):.3f}")


if __name__ == "__main__":
    main()
