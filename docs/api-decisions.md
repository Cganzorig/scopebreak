# API decisions

## 2026-07-24 initial API survey

The host has Python 3.10.12, but ControlArena 17.1.2 requires Python 3.11 or
newer. SCOPEBREAK will therefore use a `uv`-managed Python 3.12 interpreter
rather than the host interpreter. No compatibility shim for an obsolete
ControlArena release will be used.

Versions surveyed before implementation:

- Inspect AI 0.3.249 (released 2026-07-21)
- ControlArena 17.1.2 (released 2026-07-23)

Current Inspect APIs support sample-specific Docker sandbox configuration,
tool-call approval, message/token/time/working/cost limits, eval sets with
retry and resume behaviour, structured evaluation logs, and tracing. Current
ControlArena represents environments as `Setting` implementations and uses
policies plus micro-protocols for trajectory-time orchestration. Monitors that
act during a trajectory are distinct from post-hoc monitoring scorers.

The custom environment will preserve proposal-time versus execution-time
telemetry independently of framework transcripts. Tool approval is the
supported mechanism for pre-execution blocking; post-hoc scorers will never be
described as interventions.

Official sources consulted:

- <https://inspect.aisi.org.uk/llms-guide.txt>
- <https://inspect.aisi.org.uk/reference/>
- <https://control-arena.aisi.org.uk/settings.html>
- <https://control-arena.aisi.org.uk/monitors.html>
- <https://control-arena.aisi.org.uk/micro_protocols.html>
- <https://control-arena.aisi.org.uk/reference/>
- <https://pypi.org/project/inspect-ai/>
- <https://pypi.org/project/control-arena/>
