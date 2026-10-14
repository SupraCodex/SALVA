#!/usr/bin/env bash
# Wake a hosted instance up (cold start) before a demo or an evaluation session.
# Usage: ./scripts/warmup.sh [BASE_URL]      BASE_URL defaults to http://localhost:8000
set -u

BASE_URL="${1:-http://localhost:8000}"

echo "Waiting for ${BASE_URL}/api/v1/health ..."
for i in $(seq 1 60); do
  if curl -fsS --max-time 3 "${BASE_URL}/api/v1/health" >/dev/null 2>&1; then
    echo "  server is up (try ${i})"
    break
  fi
  if [ "$i" -eq 60 ]; then
    echo "  server did not answer after 60 tries" >&2
    exit 1
  fi
  sleep 2
done

curl -fsS "${BASE_URL}/api/v1/health"; echo
curl -fsS -o /dev/null "${BASE_URL}/" && echo "interface: ok"
echo "Warm-up done."
