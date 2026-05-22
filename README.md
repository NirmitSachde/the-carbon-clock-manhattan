# The Carbon Clock — Manhattan

[![Live demo](https://img.shields.io/badge/live-demo-0ED2F7?style=flat-square&logo=github&logoColor=white&labelColor=08080F)](https://nirmitsachde.github.io/the-carbon-clock-manhattan/)
[![License: MIT](https://img.shields.io/badge/license-MIT-F0F0F5?style=flat-square&labelColor=08080F)](LICENSE)
[![Data](https://img.shields.io/badge/data-NYC%20TLC%20%C2%B7%20DOT%20%C2%B7%20EPA%20AQS-F2A93B?style=flat-square&labelColor=08080F)](#data)
[![Built with deck.gl](https://img.shields.io/badge/built%20with-deck.gl-E74C3C?style=flat-square&labelColor=08080F)](https://deck.gl)
[![MapLibre + CARTO](https://img.shields.io/badge/basemap-MapLibre%20%2B%20CARTO-0ED2F7?style=flat-square&labelColor=08080F)](https://carto.com/basemaps/)
[![OSRM road snapping](https://img.shields.io/badge/road%20snapping-OSRM-F2A93B?style=flat-square&labelColor=08080F)](https://project-osrm.org/)
[![Trips](https://img.shields.io/badge/real%20trips-2.9M%20Jan--2025-E74C3C?style=flat-square&labelColor=08080F)](#data)

A multi-layer animated visualization of traffic, emissions and air quality in Manhattan over a 24-hour cycle.

**[Live Demo](https://nirmitsachde.github.io/the-carbon-clock-manhattan/)**

Inspired by the MIT Senseable City Lab's Manhattan emissions study published in Nature Sustainability (April 2026).

---

## What You Are Seeing

Three synchronized data layers, all real public data, on a dark map of Manhattan:

- **Taxi Trails** — January 2025 yellow-taxi trips from the NYC TLC dataset (3.47M total rides that month, 2.93M after Manhattan filtering), stratified by hour of day and shipped at **four selectable tiers — 25 K / 100 K / 500 K / 2.9 M**. Trip geometry is snapped to actual OpenStreetMap roads via OSRM.
- **Emission Heatmap** — 104 NYC DOT Automated Traffic Volume Count stations across Manhattan, hourly mean vehicle volumes converted to CO₂ intensity using EPA fleet-mix emission factors.
- **Air Quality Halos** — **56 NYC monitors**: 5 EPA AQS federal regulatory stations (PM2.5 parameter 88101 + NO₂ parameter 42602, 38,085 hourly readings from 2025) plus 51 PurpleAir community sensors (atmospheric PM2.5, 60-min averages over the last 7 days). Shown as halos that change color and radius with each station's typical-day hourly profile.

All three driven by one 24-hour master clock. Watch the city breathe.

---

## Key Moments

| Time   | What happens                                                                                  |
|--------|-----------------------------------------------------------------------------------------------|
| 3 AM   | Near silence. Scattered teal trails. Cool teal halos. The city is asleep.                     |
| 8 AM   | Morning rush. Trails converge on Midtown. Heatmap blooms along avenues. Halos warm to amber.  |
| 2 PM   | Steady moderate flow. Amber heatmap. Halos at yellow-amber.                                    |
| 6 PM   | Evening surge radiating outward. Peak emissions. Halos at coral.                              |
| 11 PM  | Trails thin. Heatmap fades. Halos cool back to teal. The city sleeps.                         |

---

## Quick Start

```bash
# 1. Generate synthetic data (no API keys needed)
cd preprocessing
python3 generate_synthetic_data.py

# 2. Paste your Mapbox token into index.html
# Replace YOUR_MAPBOX_TOKEN_HERE with a free pk.eyJ... token from
# https://account.mapbox.com

# 3. Serve the page (any static server works)
cd ..
python3 -m http.server 8080
# then open http://localhost:8080
```

The synthetic data is realistic enough for development and demos. To use real
data, run the three real preprocessing scripts (see below) once you have the
raw CSV/Parquet/API responses on disk.

---

## Controls

| Action            | Control                                            |
|-------------------|----------------------------------------------------|
| Play / pause      | bottom-left play button, or `Space`                |
| Scrub             | drag the time slider, or press `← / →` (15 min)    |
| Reset to midnight | reset button, or press `R`                         |
| Speed             | `1× / 2× / 5× / 10×` buttons                       |
| Toggle layers     | `Trips`, `Emissions`, `Air` pills                  |

At 1× speed, a full 24-hour cycle takes 24 minutes (one simulated minute per real second).

---

## Real Data Sources

Every layer is real public data. Nothing is mocked or synthesized.

| Layer       | Source                                                                                                                                                                                  |
|-------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Taxi trips  | [NYC TLC Yellow Taxi Trip Records](https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page) (January 2025: 3,475,226 source records → 2,933,898 Manhattan-only)                       |
| Emissions   | [NYC DOT Automated Traffic Volume Counts](https://data.cityofnewyork.us/Transportation/Automated-Traffic-Volume-Counts/7ym2-wayt) + [EPA fleet-mix factors](https://www.epa.gov/greenvehicles/greenhouse-gas-emissions-typical-passenger-vehicle) |
| Air quality | [EPA AQS hourly criteria pollutants](https://aqs.epa.gov/aqsweb/airdata/download_files.html) (PM2.5 + NO₂, federal regulatory) + [PurpleAir API](https://api.purpleair.com/) (community PM2.5) |
| Basemap     | [CARTO Dark Matter](https://carto.com/basemaps/) via [MapLibre GL JS](https://maplibre.org/) (no token, no API key)                                                                       |
| Roads       | [OpenStreetMap NY State extract](https://download.geofabrik.de/north-america/us/new-york.html) (used by OSRM for trip-geometry snapping)                                                  |

### Running the real pipeline

```bash
pip install -r preprocessing/requirements.txt

# 0. One-time: set up local OSRM via Docker (NY State OSM extract).
#    Takes ~12 min on first run; idempotent on re-runs.
preprocessing/setup_osrm.sh

# 1. Download the source files (TLC parquet, NYC DOT CSV, EPA AQS bulk).
#    URLs are in process_taxi.py / process_emissions.py / process_airquality.py.

# 2. Generate stratified tier samples from the TLC parquet.
python3 preprocessing/build_zone_centroids.py
python3 preprocessing/build_trip_tiers.py
# Snap each tier through local OSRM (parallel, ~5–80 min depending on tier size).
preprocessing/run_full_pipeline.sh   # snaps + Douglas–Peucker simplifies + packs to .bin

# 3. Emissions (CO₂ heatmap from NYC DOT counts).
python3 preprocessing/process_emissions.py

# 4. Air quality (EPA AQS + PurpleAir).
python3 preprocessing/process_airquality.py
PURPLEAIR_API_KEY=your_key python3 preprocessing/process_purpleair.py

# 5. Regenerate the data-source manifest the About modal reads.
python3 preprocessing/build_manifest.py
```

Each preprocessor writes to `data/` and is independent — re-run any one without redoing the others.

### Refresh-on-schedule (GitHub Actions)

`.github/workflows/refresh-purpleair.yml` runs every Monday at 03:00 UTC,
re-pulls the rolling 7-day PurpleAir window with the `PURPLEAIR_API_KEY`
repo secret, rebuilds `manifest.json`, and pushes back to `main` only if
the data actually changed. No manual intervention required.

---

## Architecture

```
the-carbon-clock-manhattan/
├── index.html                       # full visualization (HTML + CSS + JS, no build step)
├── data/
│   ├── manifest.json                # data provenance shown in the About modal (auto-generated)
│   ├── emissions.json               # 104 NYC DOT stations × 24 hourly snapshots
│   ├── airquality.json              # 5 EPA + 51 PurpleAir monitors × 24-hour profiles
│   └── tiers/
│       ├── trips-25k.bin            # 25,008 OSRM-snapped trips · 2.3 MB
│       ├── trips-100k.bin           # 100,008 trips · 9.2 MB
│       └── trips-500k.bin           # 484,155 trips · 44 MB
│       # trips-2m.bin (2,933,898 trips, 257 MB) hosted on Hugging Face Datasets
├── preprocessing/
│   ├── setup_osrm.sh                # Docker pull + extract/partition/customize OSRM
│   ├── run_full_pipeline.sh         # end-to-end refresh: snap all tiers + pack + manifest
│   ├── build_zone_centroids.py      # TLC taxi-zone shapefile → centroid CSV
│   ├── build_trip_tiers.py          # TLC parquet → tier-stratified raw JSONs
│   ├── snap_trips_local.py          # asyncio + 48 parallel OSRM workers
│   ├── simplify_trips.py            # Douglas–Peucker path simplification
│   ├── pack_trips_binary.py         # JSON → custom CCM1 .bin
│   ├── process_emissions.py         # NYC DOT WKT POINTs → emissions.json
│   ├── process_airquality.py        # EPA AQS bulk PM2.5 + NO₂ → airquality.json
│   ├── process_purpleair.py         # PurpleAir REST API → merged into airquality.json
│   ├── build_manifest.py            # writes data/manifest.json
│   └── requirements.txt
├── docs/og-image.png                # 1280×640 social-preview image
├── .github/workflows/               # cron-refresh PurpleAir weekly
├── ATTRIBUTION.md                   # data licensing + library credits
└── LICENSE                          # MIT
```

**Frontend stack:**
- [Deck.gl 9](https://deck.gl/) — `TripsLayer`, `HeatmapLayer`, `ScatterplotLayer`
- [MapLibre GL JS 4](https://maplibre.org/maplibre-gl-js/) — open-source, no token — paired with `deck.MapboxOverlay`
- Vanilla HTML/CSS/JS, no React, no build step. All libraries loaded from CDN.

**The master-clock pattern:** every layer reads `state.currentTime` (seconds since midnight). The animation loop advances `currentTime` by `speed * 60 * dt` each frame. Each layer interpolates between the two nearest hourly snapshots so transitions are smooth, not stepped.

---

## Design System

| Meaning            | Hex       | Used for                                            |
|--------------------|-----------|-----------------------------------------------------|
| Clean / calm       | `#0ED2F7` | Short trips, low emissions, good air                |
| Moderate / warm    | `#F2A93B` | Medium trips, moderate emissions, moderate air      |
| Intense / hot      | `#E74C3C` | Long trips, high emissions, unhealthy air           |
| Background         | `#08080F` | Page background                                     |
| Water              | `#0C0C1A` | Mapbox water layer                                  |
| Buildings          | `#141420` | Mapbox building layer                               |
| Roads              | `#1A1A2E` | Mapbox road layer                                   |

Typography: [Space Grotesk](https://fonts.google.com/specimen/Space+Grotesk) (title), [JetBrains Mono](https://fonts.google.com/specimen/JetBrains+Mono) (time display), [Inter](https://fonts.google.com/specimen/Inter) (everything else).

---

## Deployment

```bash
git init && git add . && git commit -m "Initial commit"
git remote add origin git@github.com:NirmitSachde/the-carbon-clock-manhattan.git
git push -u origin main
```

Then enable GitHub Pages in repo settings: source = `main`, folder = `/ (root)`.
**Before pushing**, make sure your Mapbox token is in `index.html` (it's a public token, so this is safe and expected).

---

## Author

Nirmit Sachde · [Portfolio](https://nirmit-sachde.vercel.app/) · [GitHub](https://github.com/NirmitSachde) · [LinkedIn](https://linkedin.com/in/nirmit-a-sachde)
