"""Generate synthetic taxi trip paths for early dev (no API keys, no Parquet).

Outputs data/trips.json. Run:  python preprocessing/generate_synthetic_data.py
"""

import json
import math
import random
from pathlib import Path

random.seed(42)

# Manhattan bounding box
LAT_MIN, LAT_MAX = 40.701, 40.878
LNG_MIN, LNG_MAX = -74.018, -73.910

# A few hub points so trips cluster realistically near Midtown/FiDi/etc.
HUBS = [
    (-73.9857, 40.7484),   # Times Square
    (-73.9772, 40.7527),   # Grand Central
    (-74.0089, 40.7128),   # FiDi
    (-73.9760, 40.7831),   # UWS
    (-73.9665, 40.7812),   # UES
]

# Diurnal demand curve: rough relative trip volume by hour 0..23
HOURLY_DEMAND = [0.15, 0.1, 0.08, 0.06, 0.07, 0.15, 0.35, 0.7, 1.0, 0.85, 0.65,
                 0.6, 0.65, 0.7, 0.7, 0.75, 0.85, 0.95, 1.0, 0.9, 0.7, 0.55, 0.45, 0.3]


def jitter(v, s):
    return v + random.uniform(-s, s)


def pick_endpoint():
    if random.random() < 0.75:
        lng, lat = random.choice(HUBS)
        return jitter(lng, 0.008), jitter(lat, 0.008)
    return random.uniform(LNG_MIN, LNG_MAX), random.uniform(LAT_MIN, LAT_MAX)


def generate_trips(total_target=1500):
    """Each trip is {path: [[lng, lat, sec_since_midnight], ...], color_intensity: 0..1}"""
    weight_sum = sum(HOURLY_DEMAND)
    per_hour = [max(1, int(round(total_target * w / weight_sum))) for w in HOURLY_DEMAND]

    trips = []
    for hour, count in enumerate(per_hour):
        for _ in range(count):
            lng1, lat1 = pick_endpoint()
            lng2, lat2 = pick_endpoint()

            start = hour * 3600 + random.randint(0, 3599)
            duration = random.randint(120, 1200)
            end = start + duration

            n = 8
            path = []
            for i in range(n):
                t = i / (n - 1)
                lng = lng1 + (lng2 - lng1) * t
                lat = lat1 + (lat2 - lat1) * t
                ts = int(start + (end - start) * t)
                path.append([round(lng, 6), round(lat, 6), ts])

            # Color by trip "length" - longer = warmer
            dist = math.hypot(lng2 - lng1, lat2 - lat1)
            color_intensity = round(min(dist * 40, 1.0), 2)

            trips.append({"path": path, "color_intensity": color_intensity})

    random.shuffle(trips)
    return trips


def main():
    out_dir = Path(__file__).resolve().parent.parent / "data"
    out_dir.mkdir(parents=True, exist_ok=True)
    trips = generate_trips()
    (out_dir / "trips.json").write_text(json.dumps(trips, separators=(",", ":")))
    print(f"Wrote {len(trips)} trips")


if __name__ == "__main__":
    main()
