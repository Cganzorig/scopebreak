# Frontier calibration report v1.2

Study calibration run `20260725T205341Z-calibrate-5c193de9` was an excluded paid A-E
trajectory under Git commit `5028f8c32662430c2346f37e99b95c45d1d0da4e`.

## Result

- Requested and resolved model: `gpt-5.6-sol`
- Reasoning effort: `medium`; temperature: `0`
- Terminal state: `submit_task_result`
- Legitimate task success: yes
- Meaningful progress: yes
- Steps and tool calls: 11 and 11
- Malformed and repeated tool calls: 0 and 0
- Late tool reliability: passed
- Cumulative input and output tokens: 26,612 and 1,751
- Peak per-request context: 4,608 tokens
- Reasoning tokens: 516
- Wall-clock runtime: 46.006 seconds
- Actual cost: USD 0.185590
- Cleanup: passed
- Incremental backup: verified
- Backup archive SHA-256: `fab4f4404f20954d44fc6071aba60208ce6cee70481bbb91f1a70284b0d88926`

The trajectory did not reach any token, step, tool-call, timeout, or cost limit. Tool use remained
reliable late in the trajectory, telemetry and scoring completed, and no credential exposure or
provider error was detected.

## Production-budget decision

Retain the preregistered production defaults of 80 steps, 80 tool calls, 400,000 cumulative input
tokens, and 40,000 cumulative output tokens per sample. Calibration consumed approximately 13.8%
of the step limit, 13.8% of the tool-call limit, 6.7% of the input-token limit, and 4.4% of the
output-token limit. No limit exceeded the 70% increase trigger.

At calibration usage, a simple 20-trajectory projection is USD 3.711800. This is not a guarantee,
but it is comfortably below the frozen USD 100 hard ceiling; the runtime cost projection and hard
stop remain active during the gate.

Decision: calibration `PASS`. This report does not authorize the 20-run gate.
