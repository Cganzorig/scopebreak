# NVIDIA A10 local-model runbook

## Purpose

The local model validates SCOPEBREAK's model-serving, OpenAI-compatible API,
Inspect tool-call, logging, scoring, and cleanup path. Qwen3-8B is not the
capable-model scientific gate and must not be used to claim behavioral absence.

Validated host: Ubuntu 22.04, NVIDIA A10 23,028 MiB, driver 580.105.08, CUDA
toolkit 12.8, and Python 3.12.13. The isolated model environment pins vLLM
0.25.1 and Ninja 1.13.0.

## Disk and memory budget

- Checkpoint: approximately 16 GB on disk, five safetensor shards.
- Model weights: 15.26 GiB reported by vLLM.
- Context: 8,192 tokens.
- GPU utilization ceiling: 0.88.
- Concurrent sequences: one.
- Validated free KV cache: 3.88 GiB / 28,208 tokens after initialization.

Keep at least 25 GB of free workspace disk for the checkpoint, caches, and
logs. Only one checkpoint is downloaded.

## Bootstrap and download

```bash
make model-bootstrap
make model-download
```

The environment defaults to `/tmp/scopebreak-vllm-env`; override it with
`SCOPEBREAK_MODEL_ENV`. The checkpoint defaults to
`results/model-cache/Qwen3-8B`; override it with `SCOPEBREAK_MODEL_DIR`.

## Start, health check, and stop

```bash
make model-start
curl --fail http://127.0.0.1:8000/health
make model-stop
```

The server binds only to loopback. It uses BF16, an 8K maximum context,
one sequence, automatic tool choice, the Hermes parser used by this
checkpoint's `<tool_call>` format, Qwen3 reasoning parsing, and thinking
disabled by default. Startup logs and the PID are under `results/`.

If startup fails, read `results/model-server.log`. The script fails on an early
process exit or an eight-minute health timeout and prints the last log lines.
On network-mounted storage, the first weight read and kernel warmup can take
several minutes. Weight prefetch and compile caches improve subsequent starts.

## Authoritative smoke trajectory

```bash
make smoke-local
```

This managed command starts the server, runs exactly one Inspect sample, and
stops the server in an exit trap. Success requires evaluation status `success`
and aggregate accuracy exactly 1.0. The validated trajectory called Bash with
`printf local-tool-ok`, received the sandbox result, called `submit`, and wrote
an `.eval` log.

Afterward verify cleanup:

```bash
nvidia-smi --query-gpu=name,memory.total,memory.used --format=csv,noheader
ss -ltn | grep ':8000' && exit 1 || true
test ! -e results/model-server.pid
```

The acceptance run ended at 0 MiB GPU memory with port 8000 closed.

## Failure modes

- `checkpoint missing`: run `make model-download`.
- `Failed to infer device type`: the process cannot see the NVIDIA driver;
  run on the GPU host, not a device-isolated sandbox.
- `No such file or directory: ninja`: rerun `make model-bootstrap`; the server
  prepends the model environment's `bin` directory to `PATH`.
- OOM: verify no other GPU job is active; do not raise utilization or context
  limits. Stop and preserve the failure log.
- Tool calls returned as plain text: retain the `hermes` parser. The generic
  Qwen3 structural parser does not match Qwen3-8B's emitted tool-call format.
