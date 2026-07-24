#!/usr/bin/env bash
set -euo pipefail

readonly ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

cleanup() {
  bash scripts/stop_model.sh || true
}
trap cleanup EXIT INT TERM

bash scripts/start_model.sh
bash scripts/run_local_smoke.sh
