# Phase 0 host report

Date: 2026-07-24 UTC

Status: **host acceptance passed; repository metadata workaround active**

Public-copy note: the ephemeral host username has been generalised. Hardware,
software, and acceptance results are preserved for reproducibility.

## Observed host

- Ubuntu 22.04.5 LTS, Linux 6.8.0-1046-nvidia
- Python 3.10.12 (a `uv`-managed Python 3.12 is required for current
  ControlArena)
- 30 logical CPUs
- 222 GiB RAM
- workspace filesystem reports far more than the required 100 GiB free
- NVIDIA A10, 23,028 MiB VRAM
- NVIDIA driver 580.105.08; driver CUDA compatibility 13.0
- Docker Engine 29.2.1
- Docker Compose 5.1.0

## Resolved host issue

The `<host-user>` account was added to the `docker` group. A process launched
with the new group ran the complete verifier, including a `--network none`
test container, successfully. Existing login shells must be renewed before
they inherit the group automatically.

## Workspace limitation

1. The workspace-provided `.git` directory was an empty, read-only mount.
   `git init .` fails while creating `.git/hooks`, so required phase commits
   cannot use the conventional path. Phase commits are stored in the writable
   `.git-data` alternate Git directory and use the workspace as their worktree.

## Safest next actions

1. Start a fresh login session before ordinary Docker commands; until then use
   `sg docker -c '<command>'`.
2. Remount or recreate the workspace with a writable `.git` directory, then
   migrate `.git-data` into `.git` for conventional Git tooling.

No model weights were downloaded and no experiment containers were started.
