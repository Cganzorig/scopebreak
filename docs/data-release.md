# Data release and reuse

## Public release boundary

The repository intentionally releases the completed frontier study's:

- frozen configuration, reports, and annotation rubric;
- observable task prompts, operator policies, messages, tool events, and
  environment outcomes;
- primary and secondary annotation JSON;
- adjudication record and agreement statistics; and
- blind-ID mapping, released only after annotation and adjudication were frozen.

The historical filename `private-blinding-map.json` describes its role during
review. It is public post-review evidence and must not be supplied to a reviewer
during a new blinded reannotation exercise.

The repository does not release provider credentials, raw authentication files,
remote backup archives, or provider-side unexposed reasoning. The observable
transcripts contain only material made available to the evaluation and review
process. Synthetic credentials, services, hostnames, and protected data are
fixtures and must not be replaced with real targets.

## Interpretation

The released trajectories are research artifacts from a small feasibility
study, not a benchmark leaderboard or a model-safety certification. Both
recorded annotation passes were Codex-based; the secondary pass was blinded but
was not independent human or cross-family validation. Reusers should preserve
that limitation and the uncertainty reported in
[feasibility-report.md](feasibility-report.md).

## Future studies

Publication exposes the environment implementation, prompts, policy wording,
clues, evaluator behavior, and prior model trajectories. A follow-up study must
therefore use newly frozen prompts, seeds, hashes, and preferably a new
environment family. It must also document possible training-data or evaluator
contamination rather than treating these released materials as hidden tests.

Before each release, scan both the current tree and Git history for credentials,
personal information, private endpoints, and host-specific paths. Recreate
archives with neutral ownership metadata where practical.
