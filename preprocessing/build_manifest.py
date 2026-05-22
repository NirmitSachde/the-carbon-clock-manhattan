"""Generate data/manifest.json from the actual data files.

The 'About this data' modal on the website reads this file at runtime so
the description of what's loaded is always in sync with what's actually
shipped. No hardcoded text in the HTML can drift out of date.

Run after any data regeneration:
    python3 preprocessing/build_manifest.py
"""

import datetime
import json
import os
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
TIERS_DIR = DATA_DIR / "tiers"


def _file_size_kb(p: Path) -> int:
    return int(p.stat().st_size / 1024) if p.exists() else 0


def _peek_bin_header(p: Path):
    """Read just the .bin header so we know N trips, M waypoints."""
    if not p.exists():
        return None
    with p.open("rb") as f:
        hdr = f.read(16)
    if len(hdr) < 16:
        return None
    magic, n_trips, n_points, _ = struct.unpack("<IIII", hdr)
    if magic != 0x43434D31:
        return None
    return n_trips, n_points


def _peek_json_trips(p: Path):
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text())
        n_trips = len(data)
        n_points = sum(len(t.get("path", [])) for t in data)
        return n_trips, n_points
    except Exception:
        return None


def tier_facts():
    # The 2M tier file is hosted on Hugging Face (too big for GitHub Pages
    # CORS) — so its .bin won't be present locally. The trip count is fixed
    # though (every Jan-2025 Manhattan ride), so we hardcode the fallback.
    HF_2M_FACTS = {
        "trips": 2933898,
        "waypoints": 20489760,
        "bin_kb": 263035,
        "json_kb": 0,
        "remote": "https://huggingface.co/datasets/NirmitSachde/carbon-clock-data",
    }
    out = {}
    for label in ["25k", "100k", "500k", "2m"]:
        bin_path = TIERS_DIR / f"trips-{label}.bin"
        json_path = TIERS_DIR / f"trips-{label}.json"
        counts = _peek_bin_header(bin_path) or _peek_json_trips(json_path)
        if counts:
            n_trips, n_points = counts
            out[label] = {
                "trips": n_trips,
                "waypoints": n_points,
                "bin_kb": _file_size_kb(bin_path),
                "json_kb": _file_size_kb(json_path),
            }
        elif label == "2m":
            out[label] = dict(HF_2M_FACTS)
        else:
            out[label] = {"trips": 0, "waypoints": 0, "bin_kb": 0, "json_kb": 0}
    return out


def emissions_facts():
    p = DATA_DIR / "emissions.json"
    if not p.exists():
        return {}
    data = json.loads(p.read_text())
    stations = len({(round(pt["lat"], 4), round(pt["lng"], 4))
                    for h in data.values() for pt in h})
    total_pts = sum(len(v) for v in data.values())
    return {
        "stations": stations,
        "snapshots": len(data),
        "rows": total_pts,
        "file_kb": _file_size_kb(p),
    }


def aq_facts():
    p = DATA_DIR / "airquality.json"
    if not p.exists():
        return {}
    data = json.loads(p.read_text())
    pollutants = sorted({pl for s in data for pl in (s.get("pollutants") or [])})
    epa = sum(1 for s in data if s.get("source") == "epa-aqs")
    pa  = sum(1 for s in data if s.get("source") == "purpleair")
    return {
        "stations": len(data),
        "epa_stations": epa,
        "purpleair_stations": pa,
        "pollutants": ", ".join(pollutants) if pollutants else "PM2.5",
        "file_kb": _file_size_kb(p),
    }


def main():
    tiers = tier_facts()
    em = emissions_facts()
    aq = aq_facts()

    # The size of the "current dataset" depends on which tier is selected at
    # runtime — we list all tiers so the modal can show what's available.
    avail = ", ".join(
        f"{t} ({tiers[t]['trips']:,} trips)" for t in ["25k", "100k", "500k", "2m"]
        if tiers[t]["trips"] > 0
    )

    manifest = {
        "generated_at": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        "layers": [
            {
                "key": "trips",
                "title": "Yellow taxi trips",
                "source": "NYC Taxi & Limousine Commission · Yellow Taxi Trip Records, January 2025",
                "source_url": "https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page",
                "facts": {
                    "Total in source month": "3,475,226 rides",
                    "Manhattan PU + DO": "2,933,898 rides",
                    "Sampling": "Stratified random sample, balanced across 24 hours",
                    "Available tiers": avail,
                    "Trip geometry": "Snapped to OpenStreetMap roads via OSRM v5",
                    "Path simplification": "Douglas–Peucker, 30 m tolerance",
                    "Coordinates": "Zone centroids from TLC taxi-zone shapefile (EPSG:2263 → WGS84)",
                    "Format": ".bin (custom CCM1, ~40% the size of JSON, parsed as typed arrays)",
                },
                "notes": "Each trail starts where a real taxi picked up and ends where it dropped off. The line in between is the actual driving route OSRM computed across OpenStreetMap.",
            },
            {
                "key": "emissions",
                "title": "Traffic-based CO₂ heatmap",
                "source": "NYC DOT · Automated Traffic Volume Counts (NYC Open Data)",
                "source_url": "https://data.cityofnewyork.us/Transportation/Automated-Traffic-Volume-Counts/7ym2-wayt",
                "facts": {
                    "Records scanned": "1,875,154 total count records",
                    "After Manhattan + year ≥ 2020 filter": "93,017 records",
                    "Unique stations": f"{em.get('stations', '–')}",
                    "Hourly snapshots": f"{em.get('snapshots', 24)} (one per hour of day)",
                    "Emission factor": "EPA fleet-mix (75 % car + 15 % light truck + 8 % heavy truck + 2 % bus → 558 g CO₂/mi)",
                    "Geometry": "WktGeom POINT in EPSG:2263 → WGS84",
                },
                "notes": "Each station's hourly mean vehicle volume is converted to grams of CO₂ using the EPA fleet-mix factor. The heatmap interpolates between adjacent hour snapshots so it morphs continuously through the day instead of snapping on the hour.",
            },
            {
                "key": "airquality",
                "title": "Air-quality monitors",
                "source": "EPA AQS (federal, regulatory) + PurpleAir (community, low-cost) · 2025",
                "source_url": "https://aqs.epa.gov/aqsweb/airdata/download_files.html",
                "facts": {
                    "Pollutants": aq.get("pollutants", "PM2.5"),
                    "Total NYC monitors":         aq.get("stations", "–"),
                    "  ↳ EPA federal":            aq.get("epa_stations", "–"),
                    "  ↳ PurpleAir community":    aq.get("purpleair_stations", "–"),
                    "PM2.5 readings scanned":     "26,940 (EPA) + 8,500+ (PurpleAir)",
                    "NO₂ readings scanned":       "11,145 (EPA only)",
                    "PurpleAir averaging":        "60-minute, last 7 days, atmospheric (outdoor-calibrated) PM2.5",
                    "Aggregation":                "Per-site median per hour-of-day (typical-day profile)",
                    "Intensity scale":            "Per-station 10th–90th percentile stretch (reveals each monitor's own daily cycle even when the absolute μg/m³ values are low)",
                    "Absolute values shown":      "Stats panel reports the raw μg/m³ and ppb — unmodified.",
                },
                "notes": "EPA's regulated network has 5 NYC monitors at hourly resolution. PurpleAir's community-sensor network adds 50+ more outdoor sites for PM2.5, all rendered as halos on the map. Combined coverage is 10× the federal-only baseline.",
            },
            {
                "key": "basemap",
                "title": "Basemap",
                "source": "CARTO Dark Matter · MapLibre GL JS",
                "source_url": "https://carto.com/basemaps/",
                "facts": {
                    "Engine": "MapLibre GL JS 4.7 (open source, no token)",
                    "Style": "CARTO Dark Matter vector tiles",
                    "Auth required": "None",
                    "Rate limit": "75 K mapviews/month free (non-commercial)",
                },
                "notes": "Replaced Mapbox in v8 to eliminate token + URL-restriction headaches for any visitor.",
            },
        ],
    }

    out_path = DATA_DIR / "manifest.json"
    out_path.write_text(json.dumps(manifest, indent=2))
    print(f"Wrote {out_path}  ({_file_size_kb(out_path)} KB)")
    print(f"Tiers detected: {avail or 'none'}")


if __name__ == "__main__":
    main()
