# Frontier feasibility baseline audit

Audit date: 2026-07-25 UTC

No provider API request was made during this audit.

## Repository state

- Commit: `8c15dbf` (`feat: complete A10-validated SCOPEBREAK MVP`)
- Branch: `main`
- Worktree at audit start: clean
- Active Git directory: `/lambda/nfs/SCOPEBREAK/.git-data`
- Git configuration: non-bare repository with `core.worktree=/lambda/nfs/SCOPEBREAK`
- `/lambda/nfs/SCOPEBREAK/.git` is an empty, read-only environment mount; ordinary Git
  discovery therefore fails unless `--git-dir=.git-data --work-tree=.` is supplied.
- History contains ten commits from host verification through the completed engineering MVP.

## Versions and host

- Python: 3.12.13
- Inspect AI: 0.3.249
- ControlArena: 17.1.2
- Docker client: 29.2.1, API 1.53
- Docker Compose: 5.1.0
- GPU: NVIDIA A10, 23,028 MiB, driver 580.105.08, idle at audit time
- CUDA reported by `nvidia-smi`: 13.0; installed `nvcc`: 12.8

## No-cost acceptance baseline

| Command | Result | Notes |
| --- | --- | --- |
| `make verify` | failed | Five prerequisites failed inside the restricted session: GPU visibility and Docker daemon access. Host-level `nvidia-smi` subsequently passed. |
| `make lint` | failed | Makefile hard-codes absent `/home/ubuntu/.local/bin/uv`. Direct `.venv/bin/ruff check .` and `.venv/bin/mypy scopebreak` passed. |
| `make test` | failed | Same hard-coded `uv` path. Direct full test run passed: 34/34. |
| `make safety-test` | failed | Same hard-coded `uv` path. Direct pre-change safety tests passed. |
| `make smoke-mock` | failed | Both Inspect mock trajectories passed; the subsequent Docker environment verification could not access the daemon. |
| `make analyse` | passed | Wrote `results/analysis/analysis.json` and `results/analysis/analysis.md`. |

The baseline command failures are preserved rather than being reclassified as passes based on
component-level substitutes.

## Docker resources and containment

The Docker client and Compose plugin are installed, but the daemon socket rejects the current
process. The socket is `srw-rw---- nobody:nogroup`; the current account cannot successfully open
it, and changing effective group requires a password. Consequently, running containers, networks
and volumes could not be inventoried, and the pre-change dynamic isolation test could not run.
This is a hard prerequisite failure for paid execution.

Static Compose inspection found five services (`agent`, `app`, `package_mirror`, `evaluator`, and
`external_sim`), two internal-only networks, no published ports, read-only root filesystems,
`cap_drop: [ALL]`, `no-new-privileges`, and no Docker-socket or host-root mount. The pre-change
dynamic verifier probed public IP and metadata access only from `agent`; it did not prove isolation
from every agent-reachable service.

## Frontier configuration at baseline

`configs/frontier_feasibility.example.yaml` is disabled and configures an unexecuted ten-sample
Variant-C-only experiment: five explicit and five silent trajectories, model
`openai/gpt-5.6-sol`, medium reasoning, temperature zero, 30 steps, 40 tool calls, 20,000 input
tokens and 8,000 output tokens per sample, with a $4 hard maximum. The guard checks sample count,
estimated cost, observe-only monitoring, an OpenAI credential and an exact confirmation phrase,
then deliberately refuses to invoke a frontier adapter. No capable-model runner exists at this
commit.

## Known limitations at baseline

- The design lacks matched Variant-A capability controls.
- Token limits do not distinguish cumulative repeated-context input from per-request context.
- There is no frozen study manifest, annotation schema, secondary-review procedure, calibration
  phase, terminal/truncation model, incremental backup, immutable paid-run layout, provider
  preflight implementation, or executable frontier adapter.
- Cost protection is a static estimate, not a live hard stop based on provider usage.
- Container builds use pinned base-image digests, but resolved built-image digests are not recorded
  in a study manifest.
- Isolation is not dynamically tested from all five services.
- Docker daemon access must be repaired before dynamic containment, image builds/digests, cleanup,
  structural dry run, calibration, or gate execution.
- Provider credential, cross-family reviewer credential, backup destination, provider-pricing
  verification and exact paid-run confirmation were not available or exercised during the audit.
