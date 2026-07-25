#!/usr/bin/env bash
set -euo pipefail

readonly ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

command -v docker >/dev/null || { echo "FAIL: docker client unavailable" >&2; exit 1; }
docker info >/dev/null 2>&1 || { echo "FAIL: Docker daemon unavailable to current user" >&2; exit 1; }

.venv/bin/pytest -q tests/safety
bash scripts/verify_environment.sh
echo "PASS: static and dynamic isolation checks from every agent-reachable service"
