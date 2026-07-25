# SCOPEBREAK

SCOPEBREAK is a safety-first research MVP for studying whether an AI agent,
given a legitimate Linux administration task, expands its operational scope to
use an unauthorised shortcut. Everything harmful is simulated: services are
local, credentials are fake, the external target is synthetic, and the rule
monitor is observe-only.

The repository provides a complete deterministic instrumentation proof and a
bounded A10 local-model pipeline proof. It does **not** establish that
instrumental scope expansion exists. The capable frontier-model experiment was
not run because no provider credential was available, so the behavioral result
is `CAPABILITY_INCONCLUSIVE`.

## What is implemented

- Inspect AI 0.3.249 and ControlArena 17.1.2 on pinned Python 3.12.
- Three package-recovery variants: no shortcut, discoverable shortcut, and a
  usable but forbidden synthetic shortcut.
- Explicit, general least-privilege, and scope-silent task prompts.
- Ground-truth proposal, execution, monitor, and environment timelines.
- Honest, permission-seeking, probing, and escalation scripted controls.
- Task-success, safe-outcome, policy-violation, escalation-stage, pre-harm,
  capability-gate, utility, and instrumental-expansion scoring.
- An observe-only rule monitor that never changes agent execution.
- A 36-trajectory deterministic mock matrix and reproducible analysis report.
- A guarded ten-sample frontier feasibility configuration with hard cost,
  sample, token, credential, and confirmation checks.
- Loopback-only vLLM 0.25.1 serving of Qwen3-8B on an NVIDIA A10, validated by
  a real Inspect Bash-tool trajectory with accuracy 1.000.

## Quick start

Install the main environment and run the deterministic acceptance path:

```bash
make bootstrap
make verify
make lint
make test
make smoke-mock
make analyse
```

Docker access may require a login shell whose group membership includes
`docker`. The dynamic environment verifier starts only internal Compose
networks and removes every container, network, and volume it creates.

## Local A10 model proof

The checkpoint is downloaded once (about 16 GB). The model environment and
server are intentionally separate from the main research environment.

```bash
make model-bootstrap
make model-download
make smoke-local
```

`make smoke-local` manages start, one bounded sample, and cleanup. The server
binds only to `127.0.0.1:8000`, caps context at 8,192 tokens and concurrency at
one, then verifies a passing Inspect task. See
[docs/a10-runbook.md](docs/a10-runbook.md).

## Frontier feasibility gate

Paid execution is disabled by default through current-commit durability receipts, a trusted-host
credential, a passing frozen calibration receipt, stage-specific confirmations, and a mandatory
two-canary review pause. Provider interruptions after model start also pause without automatic
retry; one replacement requires a fresh preflight and explicit operator recovery receipt.
Credentials are never stored in the repository or passed to containers.

```bash
make frontier-dry-run
make frontier-mock
```

The matched gate contains exactly 20 samples across A-E, A-S, C-E, and C-S. See
[docs/frontier-gate-runbook.md](docs/frontier-gate-runbook.md) for the separately confirmed
two-canary and remaining-18 stages. Running either command above makes no paid request.

## Results and analysis

Generated artifacts live below `results/` and are ignored by Git except for
the directory placeholder. Exact prompts and resolved configs are saved with
each run. To analyze a result bundle:

```bash
scopebreak analyse results/mock-smoke
# or
bash scripts/analyse.sh results/mock-smoke results/analysis
```

Reports include counts, rates, Wilson 95% intervals, stage funnels, and
boundary-condition splits. Scripted results are labeled as instrumentation
validation, not model behavior.

## Safety and cleanup

The evaluation Compose files use internal networks, no public port mappings,
read-only filesystems, dropped Linux capabilities, pinned base-image digests,
and no Docker socket or host-root mount. Public DNS, public internet, and cloud
metadata are tested as unreachable from the evaluator container.

```bash
bash scripts/verify_isolation.sh
bash scripts/clean_sandboxes.sh
```

Do not replace the synthetic secret, external simulator, or evaluator data
with real credentials or real targets. SCOPEBREAK is a research harness, not a
production security boundary.

## Scientific status

The deterministic matrix proves telemetry and scorer behavior across positive
and negative controls. The local 8B run proves serving and tool integration
only. Since the capable-model gate has zero attempted trajectories, there is no
valid estimate of model escalation frequency and no basis for building
blocking protocols, LLM monitors, or large local pilots. Those phases remain
gated on a scientifically useful feasibility result.

Read [docs/research-design.md](docs/research-design.md),
[docs/interpretation-guide.md](docs/interpretation-guide.md), and
[docs/threat-model.md](docs/threat-model.md) before interpreting outputs.
