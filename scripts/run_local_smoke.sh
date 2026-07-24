#!/usr/bin/env bash
set -euo pipefail

readonly ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

if [[ ! -s results/model-server.pid ]] || ! kill -0 "$(<results/model-server.pid)" 2>/dev/null; then
  echo "ERROR: start the bounded loopback model server first" >&2
  exit 1
fi

.venv/bin/python -m scopebreak.local_smoke
