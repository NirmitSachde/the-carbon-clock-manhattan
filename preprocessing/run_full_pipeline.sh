#!/usr/bin/env bash
# After osrm-partition finishes, this script:
#   1. runs osrm-customize
#   2. starts osrm-routed in the background (port 5000)
#   3. snaps every tier (25k, 100k, 500k, 2m) using parallel async requests
#   4. packs each into the .bin format
#   5. rebuilds data/manifest.json
#
# Intended to be run after preprocessing/setup_osrm.sh has done the
# extract+partition steps.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OSRM_DIR="$ROOT/raw/osrm"

DOCKER_RUN=(docker run --rm -v "$OSRM_DIR:/data" osrm/osrm-backend)

if [[ ! -f "$OSRM_DIR/new-york.osrm.cells" ]]; then
  echo "==> osrm-customize..."
  "${DOCKER_RUN[@]}" osrm-customize /data/new-york.osrm
fi

# Stop any prior router so the port is free.
docker ps -q --filter ancestor=osrm/osrm-backend | xargs -r docker stop >/dev/null 2>&1 || true

echo "==> Starting osrm-routed on http://localhost:5000..."
docker run --rm -d --name osrm-routed -p 5000:5000 -v "$OSRM_DIR:/data" \
  osrm/osrm-backend osrm-routed --algorithm mld /data/new-york.osrm >/dev/null

# Wait for router to become responsive (max ~30 s)
for _ in $(seq 1 60); do
  if curl -sf "http://localhost:5000/route/v1/driving/-73.99,40.75;-73.98,40.76" >/dev/null; then
    echo "==> Router is live"
    break
  fi
  sleep 0.5
done

cd "$ROOT"

# Snap each tier in turn. Order: smallest first so something useful exists
# even if a later tier fails.
for tier in 25k 100k 500k 2m; do
  raw="data/tiers/trips-$tier.raw.json"
  out_json="data/tiers/trips-$tier.json"
  out_bin="data/tiers/trips-$tier.bin"
  if [[ ! -f "$raw" ]]; then
    echo "==> [SKIP] $raw missing (run build_trip_tiers.py first)"
    continue
  fi
  echo
  echo "==================================================================="
  echo "==> Snapping tier $tier"
  echo "==================================================================="
  python3 preprocessing/snap_trips_local.py --tier "$tier" --concurrency 48
  python3 preprocessing/pack_trips_binary.py --input "$out_json" --output "$out_bin"
done

echo
echo "==> Rebuilding manifest..."
python3 preprocessing/build_manifest.py

echo
echo "==> Done. Tier file sizes:"
ls -lh data/tiers/*.bin data/tiers/*.json 2>/dev/null | grep -v '.raw.json'
