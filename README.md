# SCOPEBREAK

SCOPEBREAK is a safe, reproducible research prototype for studying when an AI
agent given only a legitimate Bash/Linux administration task expands its
operational scope and uses an unauthorised synthetic shortcut.

The MVP distinguishes explicit boundaries, general least-privilege guidance,
and scope-silent operator policy. It uses only local synthetic services and
fake secrets. Successful instrumentation does **not** establish that
instrumental scope expansion exists, and failure by a weak model is not
evidence of safety.

Development is phased. The host verifier is available now:

```bash
bash scripts/verify_host.sh
```

The remaining environment, telemetry, scorer, scripted-agent, and evaluation
commands are implemented in subsequent phases and must not be treated as
complete until their acceptance tests pass.
