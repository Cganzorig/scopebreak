#!/usr/bin/env bash
set -euo pipefail

case "${1:---dry-run}" in
  --dry-run)
    .venv/bin/python -m scopebreak.frontier_guard \
      --config configs/frontier_feasibility.example.yaml
    ;;
  --execute)
    .venv/bin/python -m scopebreak.frontier_guard \
      --config configs/frontier_feasibility.example.yaml --execute
    ;;
  *)
    printf 'usage: %s [--dry-run|--execute]\n' "$0" >&2
    exit 2
    ;;
esac
