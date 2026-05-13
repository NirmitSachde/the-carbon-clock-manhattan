"""Generate synthetic data for The Carbon Clock - Manhattan.

Produces data/trips.json, data/emissions.json, data/airquality.json.
"""

import json
import math
import random
from pathlib import Path

random.seed(42)

LAT_MIN, LAT_MAX = 40.701, 40.878
LNG_MIN, LNG_MAX = -74.018, -73.910

HUBS = [
    (-73.9857, 40.7484, "Midtown / Times Square"),
    (-73.9772, 40.7527, "Grand Central"),
    (-73.9911, 40.7505, "Penn Station"),
    (-74.0089, 40.7128, "Financial District / WTC"),
    (-73.9967, 40.7223, "SoHo"),
    (-73.9818, 40.7681, "Columbus Circle"),
    (-73.9665, 40.7812, "Upper East Side"),
    (-73.9760, 40.7831, "Upper West Side"),
    (-73.9442, 40.8116, "Harlem"),
]

HOURLY_DEMAND = [
    0.15, 0.10, 0.08, 0.06, 0.07, 0.15,
    0.35, 0.70, 1.00, 0.85, 0.65, 0.60,
    0.65, 0.70, 0.70, 0.75, 0.85, 0.95,
    1.00, 0.90, 0.70, 0.55, 0.45, 0.30,
]


def jitter(v, s):
    return v + random.uniform(-s, s)


def pick_endpoint():
    if random.random() < 0.75:
        lng, lat, _ = random.choice(HUBS)
        return jitter(lng, 0.008), jitter(lat, 0.008)
    return random.uniform(LNG_MIN, LNG_MAX), random.uniform(LAT_MIN, LAT_MAX)


def generate_trips(total_target=2000):
    weight_sum = sum(HOURLY_DEMAND)
    per_hour = [max(1, int(round(total_target * w / weight_sum))) for w in HOURLY_DEMAND]
    trips = []
    for hour, count in enumerate(per_hour):
        for _ in range(count):
            lng1, lat1 = pick_endpoint()
            lng2, lat2 = pick_endpoint()
            start = hour * 3600 + random.randint(0, 3599)
            duration = random.randint(180, 1200)
            end = start + duration

            n = 8
            path = []
            for i in range(n):
                t = i / (n - 1)
                lng = lng1 + (lng2 - lng1) * t
                lat = lat1 + (lat2 - lat1) * t
                ts = int(start + (end - start) * t)
                path.append([round(lng, 6), round(lat, 6), ts])

            dist = math.hypot(lng2 - lng1, lat2 - lat1)
            trips.append({"path": path, "color_intensity": round(min(dist * 40, 1.0), 2)})

    random.shuffle(trips)
    return trips


def generate_emission_grid(n_stations=80):
    stations = []
    for _ in range(n_stations):
        stations.append({
            "lng": round(random.uniform(LNG_MIN, LNG_MAX), 5),
            "lat": round(random.uniform(LAT_MIN, LAT_MAX), 5),
            "base": random.uniform(0.4, 1.0),
        })
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
    out = []
    for i, (lat, lng, name) in enumerate(sites):
        baseline = random.uniform(8, 18)
        pm25 = []
        for hour in range(24):
            demand = HOURLY_DEMAND[hour]
            rush_bump = 12 if (7 <= hour <= 9 or 17 <= hour <= 20) else 4 * demand
            v = max(2.0, baseline + 18 * demand + rush_bump + random.uniform(-3, 3))
            pm25.append(round(v, 1))
        intensity = [round(min(max((v - 5) / 50, 0), 1), 3) for v in pm25]
        out.append({"id": i + 1, "name": name, "lat": lat, "lng": lng,
                    "hourly_pm25": pm25, "hourly_intensity": intensity})
    return out


def main():
    out_dir = Path(__file__).resolve().parent.parent / "data"
    out_dir.mkdir(parents=True, exist_ok=True)

    trips = generate_trips()
    (out_dir / "trips.json").write_text(json.dumps(trips, separators=(",", ":")))
    print(f"Wrote {len(trips)} trips")

    emissions = generate_emission_grid()
    (out_dir / "emissions.json").write_text(json.dumps(emissions, separators=(",", ":")))
    print("Wrote emissions for 24 hourly snapshots")

    aq = generate_air_quality()
    (out_dir / "airquality.json").write_text(json.dumps(aq, separators=(",", ":")))
    print(f"Wrote {len(aq)} air quality stations")


if __name__ == "__main__":
    main()
