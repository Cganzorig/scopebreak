#!/usr/bin/env bash
set -euo pipefail

readonly ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

.venv/bin/pytest -q tests/safety
bash scripts/verify_environment.sh
echo "PASS: static and dynamic isolation checks"
