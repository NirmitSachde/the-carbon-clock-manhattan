#!/usr/bin/env bash
# Set up a local OSRM router for the NYC area.
# Steps (idempotent — safe to re-run, skips finished stages):
#   1. Download OpenStreetMap NY State extract  (~470 MB)
#   2. osrm-extract    (~6 min)
#   3. osrm-partition  (~1 min)
#   4. osrm-customize  (~1 min)
#   5. osrm-routed     (background, port 5000)
#
# After this completes you can POST/GET to http://localhost:5000/route/v1/...

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OSRM_DIR="$ROOT/raw/osrm"
PBF="$OSRM_DIR/new-york.osm.pbf"

mkdir -p "$OSRM_DIR"
cd "$OSRM_DIR"

if [[ ! -f "$PBF" ]]; then
  echo "==> Downloading NY State OSM extract..."
  curl -sL -o "$PBF" "https://download.geofabrik.de/north-america/us/new-york-latest.osm.pbf"
fi

DOCKER_RUN=(docker run --rm -v "$OSRM_DIR:/data" osrm/osrm-backend)

if [[ ! -f "new-york.osrm.edges" ]]; then
  echo "==> osrm-extract..."
  "${DOCKER_RUN[@]}" osrm-extract -p /opt/car.lua /data/new-york.osm.pbf
fi

if [[ ! -f "new-york.osrm.partition" ]]; then
  echo "==> osrm-partition..."
  "${DOCKER_RUN[@]}" osrm-partition /data/new-york.osrm
fi

if [[ ! -f "new-york.osrm.cells" ]]; then
  echo "==> osrm-customize..."
  "${DOCKER_RUN[@]}" osrm-customize /data/new-york.osrm
fi

# Kill any prior router so we don't accumulate containers.
docker ps -q --filter ancestor=osrm/osrm-backend --filter expose=5000 | xargs -r docker stop >/dev/null 2>&1 || true

echo "==> Starting osrm-routed on http://localhost:5000 (Ctrl+C kills it)..."
docker run --rm -d --name osrm-routed -p 5000:5000 -v "$OSRM_DIR:/data" \
  osrm/osrm-backend osrm-routed --algorithm mld /data/new-york.osrm
sleep 2
echo "==> Health check:"
curl -s http://localhost:5000/route/v1/driving/-73.99,40.75;-73.98,40.76 | head -c 200
echo
echo "==> Ready."
