# Attribution

The MIT [LICENSE](LICENSE) covers the code in this repository. The data shown by the visualization comes from public sources that retain their own attribution and licensing terms — listed here.

## Data sources

| Layer | Source | Licence / notes |
|---|---|---|
| Yellow taxi trips | [NYC Taxi & Limousine Commission · Yellow Taxi Trip Records, January 2025](https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page) | Public, redistributable |
| Traffic counts → CO₂ heatmap | [NYC DOT · Automated Traffic Volume Counts](https://data.cityofnewyork.us/Transportation/Automated-Traffic-Volume-Counts/7ym2-wayt) | NYC Open Data |
| EPA emission factors | [US EPA — Greenhouse Gas Emissions from a Typical Passenger Vehicle](https://www.epa.gov/greenvehicles/greenhouse-gas-emissions-typical-passenger-vehicle) | US Government public domain |
| Air quality (PM2.5 + NO₂) | [EPA Air Quality System (AQS) — hourly criteria pollutants, 2025](https://aqs.epa.gov/aqsweb/airdata/download_files.html) | US Government public domain |
| Taxi-zone shapefile | TLC Taxi Zone Lookup + Shapefile | Public, redistributable |
| Road network (for OSRM snapping) | [OpenStreetMap — New York State extract](https://download.geofabrik.de/north-america/us/new-york.html) | © OpenStreetMap contributors, [ODbL](https://www.openstreetmap.org/copyright) |

## Basemap

[CARTO Dark Matter](https://carto.com/basemaps/) — free for non-commercial use, attribution required (rendered in the page footer).

## Libraries

- [Deck.gl](https://deck.gl/) — MIT
- [MapLibre GL JS](https://maplibre.org/maplibre-gl-js/) — BSD-3-Clause
- [OSRM Backend](https://project-osrm.org/) — BSD-2-Clause (run via the official `osrm/osrm-backend` Docker image)
- [pandas](https://pandas.pydata.org/), [pyarrow](https://arrow.apache.org/), [pyproj](https://pyproj4.github.io/pyproj/), [pyshp](https://github.com/GeospatialPython/pyshp), [aiohttp](https://docs.aiohttp.org/), [huggingface_hub](https://huggingface.co/docs/huggingface_hub/) — used in the preprocessing scripts

## Larger trip-data binary hosting

The **2.9 M** trip tier (~257 MB) is hosted on Hugging Face Datasets at https://huggingface.co/datasets/NirmitSachde/carbon-clock-data because GitHub Releases switched its CDN to one that doesn't send the `Access-Control-Allow-Origin` header. HF Datasets sets CORS correctly, so the Pages-hosted page can fetch it cross-origin without any proxy.
