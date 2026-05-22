"""Generate synthetic but visually convincing data for The Carbon Clock - Manhattan.

This generator builds trips that route along an actual model of Manhattan's
avenue + cross-street grid, so trails follow the city's street pattern rather
than cutting straight across blocks. The grid is rotated ~29° east of north
(Manhattan's real orientation).

Produces data/trips.json, data/emissions.json, data/airquality.json.
Run from repo root:  python preprocessing/generate_synthetic_data.py
"""

import json
import math
import random
from pathlib import Path

random.seed(42)

# ---------------------------------------------------------------------------
# Manhattan geometry
# ---------------------------------------------------------------------------
# Approx bounding box
LAT_MIN, LAT_MAX = 40.701, 40.878
LNG_MIN, LNG_MAX = -74.018, -73.910

# Manhattan's street grid runs 29° east of true north. We work in a rotated
# coordinate system where avenues are vertical and cross-streets horizontal.
GRID_ROTATION_DEG = 29.0
GRID_ROTATION_RAD = math.radians(GRID_ROTATION_DEG)
COS_ROT = math.cos(GRID_ROTATION_RAD)
SIN_ROT = math.sin(GRID_ROTATION_RAD)

# A reference origin to anchor the rotated frame (Empire State Building).
ORIGIN_LAT = 40.7484
ORIGIN_LNG = -73.9857

# Scale to convert degrees to a roughly metric grid (meters / degree)
M_PER_DEG_LAT = 111000.0
M_PER_DEG_LNG = 111000.0 * math.cos(math.radians(ORIGIN_LAT))


def latlng_to_grid(lng, lat):
    """Rotate latlng into Manhattan-grid coordinates (x along avenues, y along streets)."""
    dx = (lng - ORIGIN_LNG) * M_PER_DEG_LNG
    dy = (lat - ORIGIN_LAT) * M_PER_DEG_LAT
    # Rotate by -29° so the grid is axis-aligned
    gx =  dx * COS_ROT + dy * SIN_ROT
    gy = -dx * SIN_ROT + dy * COS_ROT
    return gx, gy


def grid_to_latlng(gx, gy):
    """Inverse of latlng_to_grid."""
    dx = gx * COS_ROT - gy * SIN_ROT
    dy = gx * SIN_ROT + gy * COS_ROT
    return (ORIGIN_LNG + dx / M_PER_DEG_LNG,
            ORIGIN_LAT + dy / M_PER_DEG_LAT)


# Manhattan's avenues, listed west-to-east. Spacing in the rotated frame is
# roughly 80 m between adjacent avenue x-coordinates after the rotation
# (real avenues are 250-300 ft apart). We pick a representative subset and
# space them approximately to scale.
AVENUE_X = [
    # x-coord (m), avenue label
    (-1800, "12th Ave"),
    (-1530, "11th Ave"),
    (-1260, "10th Ave"),
    (-990,  "9th Ave"),
    (-720,  "8th Ave"),
    (-450,  "7th Ave"),
    (-180,  "Broadway/6th"),
    (90,    "5th Ave"),
    (360,   "Madison"),
    (630,   "Park"),
    (900,   "Lexington"),
    (1170,  "3rd Ave"),
    (1440,  "2nd Ave"),
    (1710,  "1st Ave"),
    (1980,  "FDR/York"),
]

# Cross-streets. Manhattan blocks N-S average ~80 m between numbered streets.
# We model every ~5 streets to keep the graph manageable (so trips have
# ~8-15 intersections per ride, which looks like real driving).
STREET_Y = [
    # y-coord (m), street label
    (-5200, "Battery"),       # ~ Battery Park
    (-4400, "Wall St"),
    (-3600, "Canal St"),
    (-2800, "Houston"),
    (-2000, "14th St"),
    (-1200, "23rd St"),
    (-400,  "34th St"),
    (240,   "42nd St"),
    (1040,  "57th St"),
    (1840,  "72nd St"),
    (2640,  "86th St"),
    (3440,  "96th St"),
    (4240,  "110th St"),
    (5040,  "125th St"),
    (5840,  "Harlem"),
]

# Build intersection node set.
NODES = []     # list of (avenue_idx, street_idx, lng, lat)
NODE_POS = {}  # (ai, si) -> (lng, lat)
for ai, (ax, _) in enumerate(AVENUE_X):
    for si, (sy, _) in enumerate(STREET_Y):
        lng, lat = grid_to_latlng(ax, sy)
        # Only keep nodes that fall within Manhattan's land area (approximate)
        if LAT_MIN <= lat <= LAT_MAX and LNG_MIN <= lng <= LNG_MAX:
            NODES.append((ai, si, lng, lat))
            NODE_POS[(ai, si)] = (lng, lat)


def nearest_node(lng, lat):
    """Find the closest grid intersection to a latlng point."""
    gx, gy = latlng_to_grid(lng, lat)
    best = None
    best_d2 = float("inf")
    for ai, (ax, _) in enumerate(AVENUE_X):
        for si, (sy, _) in enumerate(STREET_Y):
            if (ai, si) not in NODE_POS:
                continue
            d2 = (gx - ax) ** 2 + (gy - sy) ** 2
            if d2 < best_d2:
                best_d2 = d2
                best = (ai, si)
    return best


def route_along_grid(start_ai, start_si, end_ai, end_si):
    """Walk from (start_ai, start_si) to (end_ai, end_si) along the grid.

    Choose an L-shape: walk along the avenue first or along the cross-street
    first, randomized. Insert one or two intermediate corner-turns so the
    path doesn't always look perfectly L-shaped.
    """
    if (start_ai, start_si) == (end_ai, end_si):
        return [(start_ai, start_si)]

    path = [(start_ai, start_si)]

    # Decide turn order with some variation
    avenue_first = random.random() < 0.55

    # Optionally add one intermediate corner-jog so paths don't all look identical
    if random.random() < 0.35 and abs(end_ai - start_ai) > 1 and abs(end_si - start_si) > 1:
        # Jog: turn early, then re-align
        mid_ai = start_ai + (end_ai - start_ai) // 2
        mid_si = start_si + (end_si - start_si) // 2
        if avenue_first:
            # walk avenue to mid, turn, walk street to mid, then complete
            for s in step_range(start_si, mid_si):
                if (start_ai, s) in NODE_POS:
                    path.append((start_ai, s))
            for a in step_range(start_ai, mid_ai):
                if (a, mid_si) in NODE_POS:
                    path.append((a, mid_si))
            for s in step_range(mid_si, end_si):
                if (mid_ai, s) in NODE_POS:
                    path.append((mid_ai, s))
            for a in step_range(mid_ai, end_ai):
                if (a, end_si) in NODE_POS:
                    path.append((a, end_si))
        else:
            for a in step_range(start_ai, mid_ai):
                if (a, start_si) in NODE_POS:
                    path.append((a, start_si))
            for s in step_range(start_si, mid_si):
                if (mid_ai, s) in NODE_POS:
                    path.append((mid_ai, s))
            for a in step_range(mid_ai, end_ai):
                if (a, mid_si) in NODE_POS:
                    path.append((a, mid_si))
            for s in step_range(mid_si, end_si):
                if (end_ai, s) in NODE_POS:
                    path.append((end_ai, s))
    else:
        # Simple L-shape
        if avenue_first:
            for s in step_range(start_si, end_si):
                if (start_ai, s) in NODE_POS:
                    path.append((start_ai, s))
            for a in step_range(start_ai, end_ai):
                if (a, end_si) in NODE_POS:
                    path.append((a, end_si))
        else:
            for a in step_range(start_ai, end_ai):
                if (a, start_si) in NODE_POS:
                    path.append((a, start_si))
            for s in step_range(start_si, end_si):
                if (end_ai, s) in NODE_POS:
                    path.append((end_ai, s))

    # Deduplicate consecutive same-node entries
    dedup = [path[0]]
    for n in path[1:]:
        if n != dedup[-1]:
            dedup.append(n)
    return dedup


def step_range(a, b):
    """Inclusive range from a to b, stepping in the right direction."""
    if a == b:
        return [a]
    step = 1 if b > a else -1
    return list(range(a, b + step, step))


# ---------------------------------------------------------------------------
# Demand model
# ---------------------------------------------------------------------------

# Hub points where many taxi pickups/dropoffs cluster. Coordinates in latlng.
HUBS = [
    (-73.9857, 40.7484, "Times Square"),
    (-73.9772, 40.7527, "Grand Central"),
    (-73.9911, 40.7505, "Penn Station"),
    (-73.9934, 40.7588, "Hudson Yards"),
    (-73.9665, 40.7812, "Upper East Side"),
    (-73.9760, 40.7831, "Upper West Side"),
    (-73.9857, 40.7308, "Greenwich Village"),
    (-74.0089, 40.7128, "Financial District"),
    (-73.9967, 40.7223, "SoHo"),
    (-73.9818, 40.7681, "Columbus Circle"),
    (-73.9787, 40.7614, "Rockefeller Center"),
    (-73.9551, 40.7648, "Lenox Hill"),
    (-73.9442, 40.8116, "Harlem"),
    (-73.9762, 40.7990, "Morningside Heights"),
]

# Diurnal demand curve: relative trip count per hour
HOURLY_DEMAND = [
    0.15, 0.10, 0.08, 0.06, 0.07, 0.15,   # 0-5
    0.35, 0.70, 1.00, 0.85, 0.65, 0.60,   # 6-11
    0.65, 0.70, 0.70, 0.75, 0.85, 0.95,   # 12-17
    1.00, 0.90, 0.70, 0.55, 0.45, 0.30,   # 18-23
]


def jitter(value, scale):
    return value + random.uniform(-scale, scale)


def pick_endpoint():
    """75% chance: jitter around a hub. 25% chance: a random point inside Manhattan."""
    if random.random() < 0.75:
        lng, lat, _ = random.choice(HUBS)
        return jitter(lng, 0.006), jitter(lat, 0.006)
    return (
        random.uniform(LNG_MIN, LNG_MAX),
        random.uniform(LAT_MIN, LAT_MAX),
    )


def hav_distance_km(lng1, lat1, lng2, lat2):
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def build_trip_path(lng1, lat1, lng2, lat2):
    """Return a list of (lng, lat) waypoints that route from start to end along the grid.

    Path: start -> nearest start-intersection -> ...grid walk... -> nearest end-intersection -> end.
    """
    s_node = nearest_node(lng1, lat1)
    e_node = nearest_node(lng2, lat2)
    grid_path = route_along_grid(s_node[0], s_node[1], e_node[0], e_node[1])

    waypoints = [(lng1, lat1)]
    for node in grid_path:
        waypoints.append(NODE_POS[node])
    waypoints.append((lng2, lat2))

    # Small jitter on intermediate waypoints to avoid 1-px-wide stacked paths
    out = [waypoints[0]]
    for lng, lat in waypoints[1:-1]:
        out.append((jitter(lng, 0.00018), jitter(lat, 0.00018)))
    out.append(waypoints[-1])

    # Deduplicate consecutive points that ended up too close
    final = [out[0]]
    for p in out[1:]:
        if (p[0] - final[-1][0]) ** 2 + (p[1] - final[-1][1]) ** 2 > 1e-9:
            final.append(p)
    return final


def generate_trips(total_target=2400):
    """Produce ~total_target trips distributed across the 24h day by HOURLY_DEMAND."""
    weight_sum = sum(HOURLY_DEMAND)
    per_hour = [max(1, int(round(total_target * w / weight_sum))) for w in HOURLY_DEMAND]

    trips = []
    for hour, count in enumerate(per_hour):
        for _ in range(count):
            lng1, lat1 = pick_endpoint()
            lng2, lat2 = pick_endpoint()

            # Distance-scaled duration (Manhattan: ~3 min/km in traffic)
            dist_km = max(0.3, hav_distance_km(lng1, lat1, lng2, lat2))
            duration_sec = int(dist_km * 180 + random.uniform(60, 240))
            duration_sec = min(duration_sec, 1800)

            start_sec = hour * 3600 + random.randint(0, 3599)
            end_sec = start_sec + duration_sec

            waypoints = build_trip_path(lng1, lat1, lng2, lat2)
            n = len(waypoints)
            if n < 2:
                continue

            # Distribute timestamps evenly along the waypoint count
            path = [
                [round(lng, 6), round(lat, 6), int(start_sec + (end_sec - start_sec) * i / (n - 1))]
                for i, (lng, lat) in enumerate(waypoints)
            ]

            dist_miles = dist_km * 0.621
            color_intensity = round(min(dist_miles / 6.0, 1.0), 2)

            trips.append({"path": path, "color_intensity": color_intensity})

    random.shuffle(trips)
    return trips


def generate_emission_grid(n_stations=90):
    """Synthesize traffic count stations with rush-hour intensity."""
    stations = []
    for _ in range(n_stations):
        lng = random.uniform(LNG_MIN, LNG_MAX)
        lat = random.uniform(LAT_MIN, LAT_MAX)
        base = random.uniform(0.4, 1.0)
        stations.append({"lng": round(lng, 5), "lat": round(lat, 5), "base": base})

    by_hour = {}
    for hour in range(24):
        demand = HOURLY_DEMAND[hour]
        snapshot = []
        for s in stations:
            rush_bias = 1.15 if (7 <= hour <= 9 or 17 <= hour <= 19) else 1.0
            intensity = max(0.0, min(1.0, s["base"] * demand * rush_bias * random.uniform(0.85, 1.05)))
            snapshot.append({"lng": s["lng"], "lat": s["lat"], "intensity": round(intensity, 3)})
        by_hour[str(hour)] = snapshot
    return by_hour


def generate_air_quality():
    """A handful of EPA-style monitoring stations across Manhattan."""
    sites = [
        (40.7351, -74.0060, "PS 19 / Greenwich Village"),
        (40.8156, -73.9430, "Morrisania"),
        (40.7864, -73.9466, "Queens-MS 143"),
        (40.7281, -73.9962, "Division St"),
        (40.7654, -73.9744, "Central Park"),
        (40.8262, -73.9456, "Harlem 122 St"),
        (40.7549, -73.9840, "Times Square"),
        (40.7061, -74.0086, "Financial District"),
    ]
    stations = []
    for i, (lat, lng, name) in enumerate(sites):
        baseline = random.uniform(8, 18)
        hourly_pm25 = []
        for hour in range(24):
            demand = HOURLY_DEMAND[hour]
            rush_bump = 12 if (7 <= hour <= 9 or 17 <= hour <= 20) else 4 * demand
            v = max(2.0, baseline + 18 * demand + rush_bump + random.uniform(-3, 3))
            hourly_pm25.append(round(v, 1))
        hourly_intensity = [round(min(max((v - 5) / 50, 0), 1), 3) for v in hourly_pm25]
        stations.append({
            "id": i + 1, "name": name, "lat": lat, "lng": lng,
            "hourly_pm25": hourly_pm25, "hourly_intensity": hourly_intensity,
        })
    return stations


def main():
    out_dir = Path(__file__).resolve().parent.parent / "data"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Grid has {len(NODES)} nodes ({len(AVENUE_X)} avenues × {len(STREET_Y)} streets)")

    print("Generating taxi trips (routed along Manhattan grid)...")
    trips = generate_trips(total_target=2400)
    avg_pts = sum(len(t["path"]) for t in trips) / max(1, len(trips))
    (out_dir / "trips.json").write_text(json.dumps(trips, separators=(",", ":")))
    print(f"  -> {len(trips)} trips, avg {avg_pts:.1f} waypoints/trip, "
          f"{(out_dir / 'trips.json').stat().st_size / 1024:.1f} KB")

    print("Generating emission grid...")
    emissions = generate_emission_grid(n_stations=90)
    (out_dir / "emissions.json").write_text(json.dumps(emissions, separators=(",", ":")))
    print(f"  -> 24 hourly snapshots, "
          f"{(out_dir / 'emissions.json').stat().st_size / 1024:.1f} KB")

    print("Generating air quality stations...")
    aq = generate_air_quality()
    (out_dir / "airquality.json").write_text(json.dumps(aq, separators=(",", ":")))
    print(f"  -> {len(aq)} stations, "
          f"{(out_dir / 'airquality.json').stat().st_size / 1024:.1f} KB")

    print("\nDone. Open index.html to view.")


if __name__ == "__main__":
    main()
