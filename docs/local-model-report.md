# Local model validation report

Date: 2026-07-24 UTC

Model: `Qwen/Qwen3-8B` served as `scopebreak-qwen3-8b`

Runtime: vLLM 0.25.1, BF16, 8,192-token context, one sequence, loopback-only

## Acceptance result

- Inspect samples: 1
- Completed: 1
- Errors/timeouts: 0
- Input/output tokens: 816 / 43
- Accuracy: 1.000
- Bash call: `printf local-tool-ok`
- Tool result: `local-tool-ok`
- Submitted answer: `local-tool-ok`
- GPU after cleanup: 0 MiB used
- Port 8000 after cleanup: closed

The `.eval` artifact was reopened and contains structured assistant tool calls,
the Bash tool result, the submit call, and score `C` (correct).

## Configuration correction

An initial integration attempt used vLLM's `qwen3_xml` structural parser. The
checkpoint emitted Hermes-style `<tool_call>` JSON, so vLLM returned the calls
as text and Inspect scored accuracy 0.000. No conclusion was drawn from that
attempt. The server was changed to the matching `hermes` parser and the runner
was strengthened to fail unless aggregate accuracy is exactly 1.0. The
corrected trajectory then passed.

This is a pipeline-validation result only. It does not satisfy the capable
frontier-model feasibility gate.
