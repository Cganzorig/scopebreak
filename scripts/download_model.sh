#!/usr/bin/env bash
set -euo pipefail

readonly ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly MODEL_ENV="${SCOPEBREAK_MODEL_ENV:-/tmp/scopebreak-vllm-env}"
readonly MODEL_ID="${SCOPEBREAK_MODEL_ID:-Qwen/Qwen3-8B}"
readonly MODEL_DIR="${SCOPEBREAK_MODEL_DIR:-${ROOT_DIR}/results/model-cache/Qwen3-8B}"

if [[ ! -x "${MODEL_ENV}/bin/hf" ]]; then
  echo "ERROR: model environment missing; run scripts/bootstrap_model_env.sh" >&2
  exit 1
fi

mkdir -p "${MODEL_DIR}"
"${MODEL_ENV}/bin/hf" download "${MODEL_ID}" --local-dir "${MODEL_DIR}"
test -s "${MODEL_DIR}/config.json"
echo "Downloaded ${MODEL_ID} to ${MODEL_DIR}"
