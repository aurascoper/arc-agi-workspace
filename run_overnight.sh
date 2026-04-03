#!/bin/bash
# run_overnight.sh — Overnight codopt DSL evolution
# Runs 3 rounds x 3 branches x 180s/node in Docker via OrbStack
# Usage: ./run_overnight.sh
#   Or: nohup ./run_overnight.sh &> overnight.log &

set -eu

RUN_DATE=$(date +%Y%m%d_%H%M%S)
RUN_ID="arc-overnight-${RUN_DATE}"
RUN_ROOT="/tmp/codopt/${RUN_ID}"

cd "$(dirname "$0")"

echo "[$(date)] Starting overnight codopt: ${RUN_ID}"
echo "Run root: ${RUN_ROOT}"

# Pre-flight checks
if ! command -v codopt &>/dev/null; then
  echo "ERROR: codopt not found in PATH" >&2
  exit 1
fi

if ! docker info &>/dev/null; then
  echo "ERROR: Docker not available (is OrbStack running?)" >&2
  exit 1
fi

# Quick sanity: benchmark runs locally
echo "[$(date)] Sanity check: running benchmark..."
python3 benchmark_dsl.py
BASELINE=$(python3 -c "import json; print(json.load(open('metric.json'))['score'])")
echo "[$(date)] Baseline score: ${BASELINE}"
rm -f metric.json

# Main codopt tournament
codopt run \
  --edit dsl.py \
  --metric metric.json \
  --metric-key score \
  --command "python3 benchmark_dsl.py" \
  --test "python3 tests_dsl.py" \
  --info INFO.md \
  --branch 3 \
  --time 180 \
  --rounds 3 \
  --max-agents 4 \
  --dockerfile Dockerfile \
  --run-id "$RUN_ID" \
  --run-root "$RUN_ROOT" \
  --no-open-ui \
  --keep-worktrees

echo "[$(date)] Run completed: ${RUN_ID}"
echo "Results: ${RUN_ROOT}"

# Print summary if available
if [ -f "${RUN_ROOT}/summary.json" ]; then
  echo "--- Summary ---"
  python3 -c "import json; d=json.load(open('${RUN_ROOT}/summary.json')); print(json.dumps(d, indent=2))"
fi
