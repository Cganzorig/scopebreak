#!/usr/bin/env bash
set -euo pipefail

readonly ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ENV_DIR="${ROOT_DIR}/environments/package_recovery"

bash "${ROOT_DIR}/scripts/stop_model.sh" || true
for project in scopebreak_a scopebreak_b scopebreak_c; do
  docker compose --project-name "${project}" \
    --file "${ENV_DIR}/compose.yaml" \
    --file "${ENV_DIR}/compose.shortcut.yaml" \
    down --volumes --remove-orphans >/dev/null 2>&1 || true
done
echo "SCOPEBREAK model and Compose sandboxes are stopped."
