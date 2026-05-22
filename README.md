# The Carbon Clock — Manhattan

A multi-layer animated visualization of traffic, emissions and air quality in Manhattan over a 24-hour cycle.

**[Live Demo](https://nirmitsachde.github.io/the-carbon-clock-manhattan/)** *(once deployed)*

Inspired by the MIT Senseable City Lab's Manhattan emissions study published in Nature Sustainability (April 2026).

---

## What You Are Seeing

Three synchronized data layers, all real public data, on a dark map of Manhattan:

- **Taxi Trails** — 2,400 January 2025 yellow-taxi trips sampled from the NYC TLC dataset (3.47M total rides that month, ~2.93M after Manhattan filtering, stratified by hour of day). Trip geometry is snapped to actual OpenStreetMap roads via OSRM.
- **Emission Heatmap** — 104 NYC DOT Automated Traffic Volume Count stations across Manhattan, hourly mean vehicle volumes converted to CO₂ intensity using EPA fleet-mix emission factors.
- **Air Quality Halos** — 4 EPA AQS federal PM2.5 monitoring sites in the NYC bbox (parameter code 88101, 26,940 hourly readings from 2025), shown as halos that change color and radius with each station's typical-day hourly profile.

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

The preprocessing scripts under `preprocessing/` consume the same public datasets the proposal describes:

| Layer       | Source                                                                                                  |
|-------------|---------------------------------------------------------------------------------------------------------|
| Taxi trips  | [NYC TLC Yellow Taxi Trip Records](https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page)         |
| Emissions   | [NYC DOT Automated Traffic Volume Counts](https://data.cityofnewyork.us/Transportation/Automated-Traffic-Volume-Counts/7ym2-wayt) + [EPA emission factors](https://www.epa.gov/) |
| Air quality | [OpenAQ API](https://docs.openaq.org/) (covers EPA AirNow stations)                                     |
| Basemap     | [Mapbox GL JS](https://www.mapbox.com/) (free tier)                                                     |

### Running the real pipeline

```bash
pip install -r preprocessing/requirements.txt

# 1. Download yellow_tripdata_YYYY-MM.parquet from TLC, plus a zone_centroids.csv
#    (built from the TLC taxi zone shapefile: data.cityofnewyork.us/.../d3c1-ddgc)
python3 preprocessing/process_taxi.py \
    --parquet yellow_tripdata_2025-01.parquet \
    --centroids zone_centroids.csv

# 2. Download Automated_Traffic_Volume_Counts.csv from NYC Open Data
python3 preprocessing/process_emissions.py \
    --csv Automated_Traffic_Volume_Counts.csv \
    --manhattan-only

# 3. Set OPENAQ_API_KEY env var, then query the OpenAQ v3 API
export OPENAQ_API_KEY=your_key
python3 preprocessing/process_airquality.py
```

Each script writes its output to `data/` and is independent — you can re-run one without re-running the others.

### Optional: snap trips to real OSM roads

The synthetic generator builds trips that follow a model of Manhattan's
avenue + cross-street grid. For pixel-perfect alignment with the basemap
road network, run the OSRM snapping pass:

```bash
python3 preprocessing/snap_trips_to_roads.py
# Or test against a subset first:
python3 preprocessing/snap_trips_to_roads.py --max 100
```

This replaces each trip's path with the actual driving route between
pickup and dropoff, snapped to real OSM roads via the public OSRM demo
server. Failures fall back to the synthetic path so the file is always
valid. Expect ~30-60 minutes to snap 2400 trips due to OSRM's rate limit.

---

## Architecture

```
the-carbon-clock-manhattan/
├── index.html                       # full visualization (HTML + CSS + JS, no build tools)
├── data/
│   ├── trips.json                   # sampled taxi trip paths
│   ├── emissions.json               # 24 hourly emission snapshots
│   └── airquality.json              # AQ stations + 24h profiles
├── preprocessing/
│   ├── generate_synthetic_data.py   # stdlib-only synthetic generator; routes trips along a Manhattan grid model
│   ├── snap_trips_to_roads.py       # optional: replace synthetic paths with real OSM road geometry via OSRM
│   ├── process_taxi.py              # TLC Parquet -> trips.json
│   ├── process_emissions.py         # NYC DOT CSV -> emissions.json
│   ├── process_airquality.py        # OpenAQ v3 API -> airquality.json
│   └── requirements.txt
└── screenshots/                     # captures of key visual moments
```

**Frontend stack:**
- [Deck.gl 9](https://deck.gl/) — `TripsLayer`, `HeatmapLayer`, `ScatterplotLayer`
- [Mapbox GL JS 3](https://docs.mapbox.com/mapbox-gl-js/) — dark basemap with custom paint overrides
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
