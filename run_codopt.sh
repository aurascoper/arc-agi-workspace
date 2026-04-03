#!/bin/bash
# run_codopt.sh — Launch codopt DSL evolution tournament
# Usage: ./run_codopt.sh [rounds] [branches] [time_per_node]

ROUNDS=${1:-2}
BRANCHES=${2:-3}
TIME=${3:-120}

cd "$(dirname "$0")"

codopt run \
  --edit dsl.py \
  --metric metric.json \
  --metric-key score \
  --command "python3 benchmark_dsl.py" \
  --test "python3 tests_dsl.py" \
  --info INFO.md \
  --branch "$BRANCHES" \
  --time "$TIME" \
  --rounds "$ROUNDS" \
  --max-agents 4 \
  --dockerfile Dockerfile \
  --no-open-ui
