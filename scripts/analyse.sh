#!/usr/bin/env bash
set -euo pipefail

readonly INPUT_PATH="${1:-results/mock-smoke}"
readonly OUTPUT_PATH="${2:-results/analysis}"
.venv/bin/python -m scopebreak.analysis.report "${INPUT_PATH}" --output "${OUTPUT_PATH}"
