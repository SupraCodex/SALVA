#!/usr/bin/env bash
# Wake the server up before recording the demo video.
# Usage: ./scripts/warmup.sh [BASE_URL] [LOT_ID]
#   BASE_URL defaults to http://localhost:8000
#   LOT_ID (optional): also runs analyze + explanation once to warm everything.
set -u

BASE_URL="${1:-http://localhost:8000}"
LOT_ID="${2:-}"

echo "Waiting for ${BASE_URL}/health ..."
for i in $(seq 1 30); do
  if curl -fsS --max-time 3 "${BASE_URL}/health" >/dev/null 2>&1; then
    echo "  server is up (try ${i})"
    break
  fi
  if [ "$i" -eq 30 ]; then
    echo "  server did not answer after 30 tries" >&2
    exit 1
  fi
  sleep 1
done

echo "GET /health"
curl -fsS "${BASE_URL}/health"; echo

echo "GET /api/v1/reference"
curl -fsS "${BASE_URL}/api/v1/reference" >/dev/null && echo "  ok"

if [ -n "${LOT_ID}" ]; then
  echo "POST /api/v1/lots/${LOT_ID}/analyze"
  ANALYSIS=$(curl -fsS -X POST "${BASE_URL}/api/v1/lots/${LOT_ID}/analyze") || exit 1
  echo "  ok"
  AID=$(printf '%s' "${ANALYSIS}" | python3 -c 'import sys,json; print(json.load(sys.stdin)["id"])' 2>/dev/null || true)
  if [ -n "${AID}" ]; then
    echo "POST /api/v1/analyses/${AID}/explanation"
    curl -fsS -X POST -H 'Content-Type: application/json' \
      -d '{"lang":"fr"}' "${BASE_URL}/api/v1/analyses/${AID}/explanation" >/dev/null && echo "  ok"
  else
    echo "  (could not read analysis id, skipping explanation)"
  fi
fi

echo "Warm-up done."
