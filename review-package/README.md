# SCOPEBREAK frontier feasibility review package

Recommended reading order:

1. `feasibility-report.md` — primary results, interpretation and decision.
2. `reviewer-agreement-v1.2.md` — agreement statistics and reviewer limitations.
3. `research-design.md` — preregistered estimand, matched controls and decision rules.
4. `annotation-guide.md` — frozen annotation rubric.
5. `adjudication.json` — field-level disagreement resolutions.

Run reviewed: `20260725T210748Z-gate-2e620b22`

Frozen experiment implementation: `95452a018a06582a0e8022afb7092c99df6bf6a7`

Reporting commit: `7828f744e05762b47b192c283aaba9e64b2f164d`

This directory is the compact reporting and adjudication package. It contains
no provider credentials, raw authentication files, `.eval` logs, or remote
backup archives.

The full repository intentionally also releases the observable trajectory
packets, original annotation JSON, adjudication, and the post-review blinding
map under `annotations/20260725T210748Z-gate-2e620b22/`. The blinding map was not
provided to the secondary reviewer; it is released after review for auditability.
See the full repository's [data-release guidance](../docs/data-release.md) for
the release boundary and reuse cautions.
