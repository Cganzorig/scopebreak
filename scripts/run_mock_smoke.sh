#!/usr/bin/env bash
set -euo pipefail

export XDG_DATA_HOME="${XDG_DATA_HOME:-$PWD/results/.local-share}"
export INSPECT_NO_DISPLAY=1

.venv/bin/python scripts/verify_phase2.py
bash scripts/verify_environment.sh
.venv/bin/python -m scopebreak.mock_eval
.venv/bin/pytest -q tests/unit tests/safety

test -s results/mock-smoke/report.json
test -s results/mock-smoke/resolved-config.json
test "$(find results/mock-smoke/telemetry -name '*.jsonl' | wc -l)" -eq 36
printf 'PASS: deterministic mock end-to-end evaluation\n'
