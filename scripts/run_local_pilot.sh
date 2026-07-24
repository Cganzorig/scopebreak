#!/usr/bin/env bash
set -euo pipefail

echo "BLOCKED: local pilot scaling is disabled while the capable-model gate is CAPABILITY_INCONCLUSIVE." >&2
echo "Run the reviewed frontier feasibility gate and update docs/feasibility-report.md first." >&2
exit 2
