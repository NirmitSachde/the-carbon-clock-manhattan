"""Build zone_centroids.csv from the TLC taxi zone shapefile.

Inputs:
    raw/taxi_zones/taxi_zones.shp (+ .dbf, .prj, .shx)

Output:
    raw/zone_centroids.csv  (columns: zone_id, lat, lng, borough, zone)

The shapefile is in NY State Plane (NAD83) — EPSG:2263. We reproject to
WGS84 (lat/lng) using pyproj.
"""

import csv
import sys
from pathlib import Path

import shapefile  # pyshp
from pyproj import Transformer

ROOT = Path(__file__).resolve().parent.parent
SHP = ROOT / "raw" / "taxi_zones" / "taxi_zones.shp"
OUT = ROOT / "raw" / "zone_centroids.csv"


def ring_centroid(points):
    """Compute the (x, y) centroid of a simple polygon ring using the
    shoelace formula."""
    n = len(points)
    if n < 3:
        # degenerate ring — fall back to mean of vertices
        sx = sum(p[0] for p in points) / max(1, n)
        sy = sum(p[1] for p in points) / max(1, n)
        return sx, sy
    a = 0.0
    cx = 0.0
    cy = 0.0
    for i in range(n):
        x0, y0 = points[i]
        x1, y1 = points[(i + 1) % n]
        cross = x0 * y1 - x1 * y0
        a += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    a *= 0.5
    if abs(a) < 1e-9:
        sx = sum(p[0] for p in points) / n
        sy = sum(p[1] for p in points) / n
        return sx, sy
    cx /= (6 * a)
    cy /= (6 * a)
    return cx, cy


def main():
    if not SHP.exists():
        sys.exit(f"Shapefile not found: {SHP}")

    transformer = Transformer.from_crs("EPSG:2263", "EPSG:4326", always_xy=True)

    rows = []
    with shapefile.Reader(str(SHP)) as r:
        field_names = [f[0] for f in r.fields[1:]]   # skip deletion-flag pseudo-field
        for sr in r.shapeRecords():
            attrs = dict(zip(field_names, sr.record))
            shape = sr.shape
            if not shape.points:
                continue
            # Use the largest ring of a (multi)polygon
            best_pts, best_area = None, 0.0
            parts = list(shape.parts) + [len(shape.points)]
            for i in range(len(parts) - 1):
                ring = shape.points[parts[i]:parts[i + 1]]
                cx, cy = ring_centroid(ring)
                area = 0.0
                for j in range(len(ring)):
                    x0, y0 = ring[j]
                    x1, y1 = ring[(j + 1) % len(ring)]
                    area += x0 * y1 - x1 * y0
                area = abs(area * 0.5)
                if area > best_area:
                    best_area = area
                    best_pts = (cx, cy)
            if best_pts is None:
                continue
            cx, cy = best_pts
            lng, lat = transformer.transform(cx, cy)
            rows.append({
                "zone_id": int(attrs.get("LocationID") or attrs.get("LocationId") or attrs.get("OBJECTID")),
                "lat": round(lat, 6),
                "lng": round(lng, 6),
                "borough": attrs.get("borough") or attrs.get("Borough") or "",
                "zone": attrs.get("zone") or attrs.get("Zone") or "",
            })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["zone_id", "lat", "lng", "borough", "zone"])
        w.writeheader()
        w.writerows(rows)

    print(f"Wrote {len(rows)} zone centroids -> {OUT}")
    # Sanity: first few Manhattan zones
    manh = [r for r in rows if r["borough"] == "Manhattan"]
    print(f"Manhattan zones: {len(manh)}")
    for r in manh[:3]:
        print(f"  {r['zone_id']:>3} ({r['lat']}, {r['lng']})  {r['zone']}")


if __name__ == "__main__":
    main()
