"""Pack trips.json into a compact binary file for the browser.

Output layout (little-endian, single .bin file):

  Header (16 bytes):
    Uint32  magic       = 0x43434D31  ('CCM1' = Carbon Clock Manhattan v1)
    Uint32  num_trips   N
    Uint32  num_points  M  (total waypoints across all trips)
    Uint32  reserved    0

  Trip index (4 bytes × (N + 1)):
    Uint32  start_offset[0..N]   — point-array offset where each trip begins;
                                    trip i waypoint count = start_offset[i+1] - start_offset[i]

  Per-trip color (4 bytes × N):
    Uint8   r, g, b, a   — pre-baked RGBA

  Points (12 bytes × M):
    Float32 lng
    Float32 lat
    Float32 seconds_since_midnight

Why this layout:
  - Deck.gl TripsLayer accepts data as `{startIndices, attributes}` for binary
    mode. The trip index doubles as startIndices. The point array maps 1:1 to
    a Float32Array buffer that can be passed straight to the GPU.
  - No JSON parse cost. Loading a 5–50 MB .bin is just an ArrayBuffer fetch.
  - About 2.5–3× smaller than equivalent JSON before gzip; comparable after
    gzip but parse time drops from ~1 s to ~20 ms at the 100k-trip tier.
"""

import argparse
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

MAGIC = 0x43434D31


def pack(trips, out_path: Path):
    n_trips = len(trips)
    n_points = sum(len(t["path"]) for t in trips)

    # Build the buffers
    header = struct.pack("<IIII", MAGIC, n_trips, n_points, 0)

    start_offsets = []
    colors = bytearray()
    points = bytearray()

    cursor = 0
    for t in trips:
        start_offsets.append(cursor)
        # Pre-baked color: intensity (0..1) -> teal -> amber -> coral RGB
        intensity = float(t.get("color_intensity", 0.5))
        intensity = max(0.0, min(1.0, intensity))
        if intensity <= 0.5:
            k = intensity / 0.5
            r = int(round(14 + (242 - 14) * k))
            g = int(round(210 + (169 - 210) * k))
            b = int(round(247 + (59 - 247) * k))
        else:
            k = (intensity - 0.5) / 0.5
            r = int(round(242 + (231 - 242) * k))
            g = int(round(169 + (76 - 169) * k))
            b = int(round(59 + (60 - 59) * k))
        colors.append(r); colors.append(g); colors.append(b); colors.append(220)

        for lng, lat, ts in t["path"]:
            points += struct.pack("<fff", float(lng), float(lat), float(ts))
            cursor += 1

    start_offsets.append(cursor)  # sentinel for last trip's end

    trip_index = struct.pack(f"<{n_trips + 1}I", *start_offsets)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("wb") as f:
        f.write(header)
        f.write(trip_index)
        f.write(colors)
        f.write(points)

    return n_trips, n_points, out_path.stat().st_size


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=str(ROOT / "data" / "trips.json"))
    ap.add_argument("--output", default=str(ROOT / "data" / "trips.bin"))
    args = ap.parse_args()

    in_path = Path(args.input)
    if not in_path.exists():
        sys.exit(f"Input not found: {in_path}")
    out_path = Path(args.output)

    trips = json.loads(in_path.read_text())
    n_trips, n_points, size = pack(trips, out_path)

    json_size = in_path.stat().st_size
    print(f"Packed {n_trips:,} trips, {n_points:,} waypoints")
    print(f"  JSON: {json_size / 1024:.1f} KB")
    print(f"  BIN:  {size / 1024:.1f} KB  ({100 * size / json_size:.1f}% of JSON)")
    print(f"  -> {out_path}")


if __name__ == "__main__":
    main()
