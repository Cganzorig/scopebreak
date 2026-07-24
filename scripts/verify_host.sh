#!/usr/bin/env bash
set -uo pipefail

# SCOPEBREAK Phase 0 host verifier. This script is intentionally read-only.
# It reports every required check and exits non-zero when a hard prerequisite
# is missing. Run it as the same user that will run evaluations.

failures=0

section() {
  printf '\n[%s]\n' "$1"
}

run_optional() {
  local label=$1
  shift
  section "$label"
  if ! "$@"; then
    printf 'CHECK_FAILED: %s\n' "$label" >&2
    failures=$((failures + 1))
  fi
}

section "kernel"
uname -a

section "operating-system"
cat /etc/os-release

section "python"
python3 --version
if [[ -x .venv/bin/python ]]; then
  .venv/bin/python --version
elif [[ -x .uv-python/cpython-3.12.13-linux-x86_64-gnu/bin/python3.12 ]]; then
  .uv-python/cpython-3.12.13-linux-x86_64-gnu/bin/python3.12 --version
else
  printf 'CHECK_FAILED: project Python 3.12 is not installed\n' >&2
  failures=$((failures + 1))
fi

section "disk"
df -h "${SCOPEBREAK_WORKSPACE:-.}"
available_kib=$(df -Pk "${SCOPEBREAK_WORKSPACE:-.}" | awk 'NR == 2 {print $4}')
if [[ ! "$available_kib" =~ ^[0-9]+$ ]] || (( available_kib < 100 * 1024 * 1024 )); then
  printf 'CHECK_FAILED: less than 100 GiB free in workspace filesystem\n' >&2
  failures=$((failures + 1))
fi

section "memory"
free -h

section "cpu"
nproc

run_optional "gpu" nvidia-smi

section "gpu-summary"
if ! nvidia-smi \
  --query-gpu=name,memory.total,driver_version \
  --format=csv,noheader; then
  printf 'CHECK_FAILED: GPU summary unavailable\n' >&2
  failures=$((failures + 1))
fi

section "cuda-version"
if command -v nvcc >/dev/null 2>&1; then
  nvcc --version
else
  # The driver-supported CUDA version is still reported by nvidia-smi.
  nvidia-smi | sed -n '1,3p' || true
  printf 'INFO: nvcc is not installed; using driver CUDA compatibility above\n'
fi

run_optional "docker-client-and-server" docker version
run_optional "docker-compose" docker compose version

section "docker-current-user"
if docker info >/dev/null 2>&1; then
  printf 'PASS: current user can access the Docker daemon\n'
else
  printf 'CHECK_FAILED: current user cannot access the Docker daemon\n' >&2
  failures=$((failures + 1))
fi

section "docker-test-container"
if docker run --rm --network none hello-world >/dev/null; then
  printf 'PASS: Docker started and removed a network-isolated test container\n'
else
  printf 'CHECK_FAILED: Docker test container failed\n' >&2
  failures=$((failures + 1))
fi

section "local-model-ports"
for port in ${SCOPEBREAK_MODEL_PORTS:-8000}; do
  if command -v ss >/dev/null 2>&1 && ss -H -ltn "sport = :$port" | grep -q .; then
    printf 'CHECK_FAILED: TCP port %s is already listening\n' "$port" >&2
    failures=$((failures + 1))
  else
    printf 'PASS: TCP port %s is free\n' "$port"
  fi
done

section "summary"
if (( failures > 0 )); then
  printf 'FAIL: %d prerequisite check(s) failed\n' "$failures" >&2
  exit 1
fi
printf 'PASS: all Phase 0 host prerequisites passed\n'
