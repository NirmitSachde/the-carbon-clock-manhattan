"""Generate synthetic but visually convincing data for The Carbon Clock - Manhattan.

Produces data/trips.json, data/emissions.json, data/airquality.json so the
visualization runs immediately, before real TLC/DOT/OpenAQ data is processed.

Run from repo root:  python preprocessing/generate_synthetic_data.py
"""

import json
import math
import os
import random
from pathlib import Path

random.seed(42)

# Manhattan bounding box (approximate)
LAT_MIN, LAT_MAX = 40.701, 40.878
LNG_MIN, LNG_MAX = -74.018, -73.910

# Manhattan's street grid is rotated ~29 degrees east of north
GRID_ROTATION_RAD = math.radians(29.0)

# Hub points where many trips start/end (in lng, lat)
HUBS = [
    (-73.9857, 40.7484, "Midtown / Times Square"),
    (-73.9772, 40.7527, "Grand Central"),
    (-73.9911, 40.7505, "Penn Station"),
    (-73.9934, 40.7505, "Hudson Yards"),
    (-73.9665, 40.7812, "Upper East Side"),
    (-73.9760, 40.7831, "Upper West Side"),
    (-73.9857, 40.7308, "Greenwich Village"),
    (-74.0089, 40.7128, "Financial District / WTC"),
    (-73.9967, 40.7223, "SoHo"),
    (-73.9818, 40.7681, "Columbus Circle"),
    (-73.9787, 40.7614, "Rockefeller Center"),
    (-73.9551, 40.7648, "Lenox Hill"),
    (-73.9762, 40.7990, "Morningside Heights"),
    (-73.9442, 40.8116, "Harlem"),
]

# Diurnal demand curve: relative trip volume per hour (0..23)
# Two peaks (morning ~8am, evening ~6pm), trough at 3-4am
HOURLY_DEMAND = [
    0.15, 0.10, 0.08, 0.06, 0.07, 0.15,   # 0-5
    0.35, 0.70, 1.00, 0.85, 0.65, 0.60,   # 6-11
    0.65, 0.70, 0.70, 0.75, 0.85, 0.95,   # 12-17
    1.00, 0.90, 0.70, 0.55, 0.45, 0.30,   # 18-23
]


def jitter(value, scale):
    return value + random.uniform(-scale, scale)


def pick_endpoint():
    """75% chance: near a hub. 25% chance: anywhere in Manhattan."""
    if random.random() < 0.75:
        lng, lat, _ = random.choice(HUBS)
        return jitter(lng, 0.008), jitter(lat, 0.008)
    return (
        random.uniform(LNG_MIN, LNG_MAX),
        random.uniform(LAT_MIN, LAT_MAX),
    )


def snap_to_grid_path(lng1, lat1, lng2, lat2, n_points=10):
    """Build a Manhattan-style path: move along one grid axis, then the other,
    so trips follow an L-shape that looks like real street travel rather than
    straight diagonals."""
    # Rotate into grid-aligned coordinates
    cos_r = math.cos(-GRID_ROTATION_RAD)
    sin_r = math.sin(-GRID_ROTATION_RAD)

    def to_grid(lng, lat):
        return (lng * cos_r - lat * sin_r, lng * sin_r + lat * cos_r)

    def from_grid(x, y):
        cr = math.cos(GRID_ROTATION_RAD)
        sr = math.sin(GRID_ROTATION_RAD)
        return (x * cr - y * sr, x * sr + y * cr)

    x1, y1 = to_grid(lng1, lat1)
    x2, y2 = to_grid(lng2, lat2)

    # L-shape with a small randomized elbow
    elbow_frac = random.uniform(0.4, 0.7)
    if random.random() < 0.5:
        xm, ym = x1 + (x2 - x1) * elbow_frac, y1
    else:
        xm, ym = x1, y1 + (y2 - y1) * elbow_frac

    # Generate n_points along start -> elbow -> end
    def lerp_segment(a, b, k):
        return [a + (b - a) * (i / (k - 1)) for i in range(k)]

    k1 = max(2, n_points // 2)
    k2 = n_points - k1 + 1
    xs = lerp_segment(x1, xm, k1) + lerp_segment(xm, x2, k2)[1:]
    ys = lerp_segment(y1, ym, k1) + lerp_segment(ym, y2, k2)[1:]

    pts = []
    for x, y in zip(xs, ys):
        lng, lat = from_grid(x, y)
        # tiny jitter so trips don't perfectly overlap
        pts.append((jitter(lng, 0.0003), jitter(lat, 0.0003)))
    return pts


def hav_distance_km(lng1, lat1, lng2, lat2):
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def generate_trips(total_target=4000):
    """Generate ~total_target trips, distributed across the 24h day per HOURLY_DEMAND."""
    # Convert demand curve to trip counts
    weight_sum = sum(HOURLY_DEMAND)
    per_hour = [max(1, int(round(total_target * w / weight_sum))) for w in HOURLY_DEMAND]

    trips = []
    for hour, count in enumerate(per_hour):
        for _ in range(count):
            lng1, lat1 = pick_endpoint()
            lng2, lat2 = pick_endpoint()

            # Trip duration: scaled by distance (rough proxy: ~3 min/km in Manhattan)
            dist_km = max(0.2, hav_distance_km(lng1, lat1, lng2, lat2))
            duration_sec = int(dist_km * 180 + random.uniform(60, 240))
            duration_sec = min(duration_sec, 1800)  # cap at 30 min

            start_sec = hour * 3600 + random.randint(0, 3599)
            end_sec = start_sec + duration_sec

            path_xy = snap_to_grid_path(lng1, lat1, lng2, lat2, n_points=7)
            timestamps = [
                int(start_sec + (end_sec - start_sec) * i / (len(path_xy) - 1))
                for i in range(len(path_xy))
            ]
            path = [[round(lng, 6), round(lat, 6), ts] for (lng, lat), ts in zip(path_xy, timestamps)]

            # Color intensity: longer = warmer
            dist_miles = dist_km * 0.621
            color_intensity = round(min(dist_miles / 6.0, 1.0), 2)

            trips.append({"path": path, "color_intensity": color_intensity})

    random.shuffle(trips)
    return trips


def generate_emission_grid(n_stations=90):
    """Place pseudo-traffic-count stations across Manhattan with rush-hour intensity."""
    stations = []
    # Bias placement toward major corridors (avenues run roughly N-S along grid axis)
    for _ in range(n_stations):
        lng = random.uniform(LNG_MIN, LNG_MAX)
        lat = random.uniform(LAT_MIN, LAT_MAX)
        # Per-station base traffic weight (some are major intersections)
        base = random.uniform(0.4, 1.0)
        stations.append({"lng": round(lng, 5), "lat": round(lat, 5), "base": base})

    # For each hour, scale by HOURLY_DEMAND with smooth interpolation
    by_hour = {}
    for hour in range(24):
        snapshot = []
        demand = HOURLY_DEMAND[hour]
        for s in stations:
            # Add a little spatial variation: some hotspots are stronger in rush, calmer late
            rush_bias = 1.0
            if 7 <= hour <= 9 or 17 <= hour <= 19:
                rush_bias = 1.15
            intensity = s["base"] * demand * rush_bias * random.uniform(0.85, 1.05)
            intensity = max(0.0, min(intensity, 1.0))
            snapshot.append({"lng": s["lng"], "lat": s["lat"], "intensity": round(intensity, 3)})
        by_hour[str(hour)] = snapshot
    return by_hour


def generate_air_quality():
    """A handful of EPA-style monitoring stations across Manhattan."""
    # Known approximate locations of real NYC AQ monitoring sites
    sites = [
        (40.7351, -74.0060, "PS 19 / Greenwich Village"),
        (40.8156, -73.9430, "Morrisania (Bronx-adjacent)"),
        (40.7864, -73.9466, "Queens-MS 143 (Manhattan-adjacent)"),
        (40.7281, -73.9962, "Division St"),
        (40.7654, -73.9744, "Central Park"),
        (40.8262, -73.9456, "Harlem 122 St"),
        (40.7549, -73.9840, "Times Square"),
        (40.7061, -74.0086, "Financial District"),
    ]

    stations = []
    for i, (lat, lng, name) in enumerate(sites):
        # Build a 24h PM2.5 profile (ug/m3): WHO guideline ~15, EPA unhealthy ~55
        # Rush hours -> higher PM2.5
        hourly_pm25 = []
        baseline = random.uniform(8, 18)
        for hour in range(24):
            demand = HOURLY_DEMAND[hour]
            rush_bump = 12 if (7 <= hour <= 9 or 17 <= hour <= 20) else 4 * demand
            noise = random.uniform(-3, 3)
            pm25 = max(2.0, baseline + 18 * demand + rush_bump + noise)
            hourly_pm25.append(round(pm25, 1))

        # Normalize to 0..1 intensity (5 ug/m3 floor, 55 ug/m3 ceiling)
        hourly_intensity = [
            round(min(max((v - 5) / 50, 0), 1), 3) for v in hourly_pm25
        ]

        stations.append({
            "id": i + 1,
            "name": name,
            "lat": lat,
            "lng": lng,
            "hourly_pm25": hourly_pm25,
            "hourly_intensity": hourly_intensity,
        })
    return stations


def main():
    out_dir = Path(__file__).resolve().parent.parent / "data"
    out_dir.mkdir(parents=True, exist_ok=True)

    print("Generating taxi trips...")
    trips = generate_trips(total_target=4000)
    (out_dir / "trips.json").write_text(json.dumps(trips, separators=(",", ":")))
    print(f"  -> {len(trips)} trips, {(out_dir / 'trips.json').stat().st_size / 1024:.1f} KB")

    print("Generating emission grid...")
    emissions = generate_emission_grid(n_stations=90)
    (out_dir / "emissions.json").write_text(json.dumps(emissions, separators=(",", ":")))
    print(f"  -> 24 hourly snapshots, {(out_dir / 'emissions.json').stat().st_size / 1024:.1f} KB")

    print("Generating air quality stations...")
    aq = generate_air_quality()
    (out_dir / "airquality.json").write_text(json.dumps(aq, separators=(",", ":")))
    print(f"  -> {len(aq)} stations, {(out_dir / 'airquality.json').stat().st_size / 1024:.1f} KB")

    print("\nDone. Open index.html to view.")


if __name__ == "__main__":
    main()
