#!/usr/bin/env bash
set -euo pipefail

readonly ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly PID_FILE="${ROOT_DIR}/results/model-server.pid"

if [[ ! -s "${PID_FILE}" ]]; then
  echo "Model server is not running (no PID file)."
  exit 0
fi

readonly SERVER_PID="$(<"${PID_FILE}")"
if kill -0 "${SERVER_PID}" 2>/dev/null; then
  kill "${SERVER_PID}"
  for _ in $(seq 1 30); do
    if ! kill -0 "${SERVER_PID}" 2>/dev/null; then
      break
    fi
    sleep 1
  done
fi
rm -f "${PID_FILE}"
echo "Stopped model server PID ${SERVER_PID}."
