#!/usr/bin/env bash
set -euo pipefail

readonly ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly MODEL_ENV="${SCOPEBREAK_MODEL_ENV:-/tmp/scopebreak-vllm-env}"
readonly MODEL_DIR="${SCOPEBREAK_MODEL_DIR:-${ROOT_DIR}/results/model-cache/Qwen3-8B}"
readonly SERVED_NAME="${SCOPEBREAK_SERVED_MODEL:-scopebreak-qwen3-8b}"
readonly HOST="127.0.0.1"
readonly PORT="${SCOPEBREAK_MODEL_PORT:-8000}"
readonly PID_FILE="${ROOT_DIR}/results/model-server.pid"
readonly LOG_FILE="${ROOT_DIR}/results/model-server.log"

if [[ ! -x "${MODEL_ENV}/bin/vllm" ]]; then
  echo "ERROR: model environment missing; run scripts/bootstrap_model_env.sh" >&2
  exit 1
fi
if [[ ! -s "${MODEL_DIR}/config.json" ]]; then
  echo "ERROR: checkpoint missing; run scripts/download_model.sh" >&2
  exit 1
fi
if [[ -s "${PID_FILE}" ]] && kill -0 "$(<"${PID_FILE}")" 2>/dev/null; then
  echo "ERROR: model server already running with PID $(<"${PID_FILE}")" >&2
  exit 1
fi

mkdir -p "${ROOT_DIR}/results"
: >"${LOG_FILE}"
nohup env PATH="${MODEL_ENV}/bin:${PATH}" \
  HF_HOME="${ROOT_DIR}/results/model-cache/huggingface" \
  VLLM_LOGGING_LEVEL=INFO \
  "${MODEL_ENV}/bin/vllm" serve "${MODEL_DIR}" \
  --served-model-name "${SERVED_NAME}" \
  --host "${HOST}" \
  --port "${PORT}" \
  --dtype bfloat16 \
  --max-model-len 8192 \
  --gpu-memory-utilization 0.88 \
  --max-num-seqs 1 \
  --safetensors-load-strategy prefetch \
  --enable-auto-tool-choice \
  --tool-call-parser hermes \
  --reasoning-parser qwen3 \
  --default-chat-template-kwargs '{"enable_thinking":false}' \
  >"${LOG_FILE}" 2>&1 &
readonly SERVER_PID=$!
echo "${SERVER_PID}" >"${PID_FILE}"

for _ in $(seq 1 240); do
  if ! kill -0 "${SERVER_PID}" 2>/dev/null; then
    echo "ERROR: model server exited during startup" >&2
    tail -80 "${LOG_FILE}" >&2
    rm -f "${PID_FILE}"
    exit 1
  fi
  if "${MODEL_ENV}/bin/python" - "${HOST}" "${PORT}" <<'PY'
import sys
from urllib.request import urlopen
from urllib.error import URLError

try:
    with urlopen(f"http://{sys.argv[1]}:{sys.argv[2]}/health", timeout=2) as response:
        raise SystemExit(0 if response.status == 200 else 1)
except (OSError, URLError):
    raise SystemExit(1) from None
PY
  then
    echo "Model server ready at http://${HOST}:${PORT}/v1 (PID ${SERVER_PID})"
    exit 0
  fi
  sleep 2
done

echo "ERROR: model server did not become healthy within 8 minutes" >&2
tail -80 "${LOG_FILE}" >&2
exit 1
