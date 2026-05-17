"""Process NYC DOT Automated Traffic Volume Counts CSV -> data/emissions.json.

Pipeline:
  1. Read traffic counts CSV (columns vary; we normalize on the way in).
  2. Aggregate to (lat, lng, hour) -> mean vehicle count.
  3. Apply EPA fleet-mix emission factor to estimate grams CO2.
  4. Normalize to 0-1 intensity scale.
  5. Write {hour_str: [{lng, lat, intensity}, ...]} to data/emissions.json.

Source CSV:
  https://data.cityofnewyork.us/Transportation/Automated-Traffic-Volume-Counts/7ym2-wayt
"""

import argparse
import json
from pathlib import Path

import pandas as pd

DEFAULT_CSV = "Automated_Traffic_Volume_Counts.csv"
DEFAULT_OUT = Path(__file__).resolve().parent.parent / "data" / "emissions.json"

# EPA emission factors (g CO2 / vehicle mile)
EMISSION_FACTORS = {
    "car": 400,
    "light_truck": 540,
    "heavy_truck": 1600,
    "bus": 2200,
}
FLEET_MIX = {"car": 0.75, "light_truck": 0.15, "heavy_truck": 0.08, "bus": 0.02}
AVG_EMISSION_FACTOR = sum(FLEET_MIX[k] * EMISSION_FACTORS[k] for k in FLEET_MIX)
AVG_TRIP_MILES = 2.0  # rough miles per vehicle past a count station


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Map various NYC DOT column-name variants to the canonical ones we use."""
    rename = {}
    for c in df.columns:
        lc = c.lower()
        if lc in ("hh", "hour"):
            rename[c] = "hour"
        elif lc in ("vol", "volume", "count"):
            rename[c] = "vol"
        elif lc in ("lat", "latitude"):
            rename[c] = "lat"
        elif lc in ("lng", "long", "longitude", "lon"):
            rename[c] = "lng"
        elif lc == "boro":
            rename[c] = "boro"
    return df.rename(columns=rename)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=DEFAULT_CSV)
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--manhattan-only", action="store_true",
                    help="If Boro column exists, keep only Manhattan rows.")
    args = ap.parse_args()

    print(f"Reading {args.csv}...")
    df = pd.read_csv(args.csv)
    df = normalize_columns(df)

    required = {"hour", "vol", "lat", "lng"}
    missing = required - set(df.columns)
    if missing:
        raise SystemExit(f"Missing required columns after normalization: {missing}. "
                         f"Got: {list(df.columns)}")

    if args.manhattan_only and "boro" in df.columns:
        df = df[df["boro"].astype(str).str.lower().str.contains("manhattan")]

    df["lat"] = df["lat"].round(4)
    df["lng"] = df["lng"].round(4)

    print(f"  -> {len(df):,} count records, "
          f"{df.groupby(['lat', 'lng']).ngroups} unique stations")

    hourly = (
        df.groupby(["lat", "lng", "hour"])["vol"].mean().reset_index()
    )
    hourly["emissions_g"] = hourly["vol"] * AVG_EMISSION_FACTOR * AVG_TRIP_MILES

    max_emissions = hourly["emissions_g"].max()
    if max_emissions == 0 or pd.isna(max_emissions):
        raise SystemExit("No traffic volume found; cannot normalize.")
    hourly["intensity"] = (hourly["emissions_g"] / max_emissions).round(3)

    print(f"Building 24 hourly snapshots...")
    result = {}
    for hour in range(24):
        snapshot = hourly[hourly["hour"] == hour]
        result[str(hour)] = [
            {"lng": float(r.lng), "lat": float(r.lat), "intensity": float(r.intensity)}
            for r in snapshot.itertuples(index=False)
        ]

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w") as f:
        json.dump(result, f, separators=(",", ":"))

    total_points = sum(len(v) for v in result.values())
    print(f"Wrote {total_points:,} (station, hour) points -> {out_path} "
          f"({out_path.stat().st_size / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
