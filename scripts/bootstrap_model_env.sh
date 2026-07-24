#!/usr/bin/env bash
set -euo pipefail

readonly VLLM_VERSION="0.25.1"
readonly NINJA_VERSION="1.13.0"
readonly ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly MODEL_ENV="${SCOPEBREAK_MODEL_ENV:-/tmp/scopebreak-vllm-env}"
readonly UV_BIN="${UV_BIN:-/home/ubuntu/.local/bin/uv}"
readonly MODEL_UV_CACHE="${UV_CACHE_DIR:-/tmp/scopebreak-uv-cache}"

if [[ ! -x "${UV_BIN}" ]]; then
  echo "ERROR: uv is not installed at ${UV_BIN}" >&2
  exit 1
fi

if [[ ! -x "${MODEL_ENV}/bin/python" ]]; then
  UV_CACHE_DIR="${MODEL_UV_CACHE}" UV_PYTHON_INSTALL_DIR="${ROOT_DIR}/.uv-python" \
    "${UV_BIN}" venv --python 3.12 "${MODEL_ENV}"
fi
UV_CACHE_DIR="${MODEL_UV_CACHE}" "${UV_BIN}" pip install \
  --python "${MODEL_ENV}/bin/python" \
  "vllm==${VLLM_VERSION}" \
  "ninja==${NINJA_VERSION}"
"${MODEL_ENV}/bin/python" -c \
  "from importlib.metadata import version; print('vllm', version('vllm'))"
"${MODEL_ENV}/bin/ninja" --version
