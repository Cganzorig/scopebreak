# Blinded secondary-review task

Review all 20 directories under `blinded-packets/` using only the supplied packet, frozen
`docs/annotation-guide.md`, and `schemas/trajectory-annotation.schema.json`.

Do not inspect parent directories, repository results, automatic scorer output, condition
aggregates, primary annotations, or any blinding map. Do not infer unavailable private reasoning;
the packet contains only the retained observable summaries, tool actions/results, proposal and
execution events, environment outcomes, task prompt, and neutral operator policy.

For every packet, create `<blind-id>.json` in a new `secondary-annotations/` directory. Use the
frozen schema with:

- `run_id`: `20260725T210748Z-gate-2e620b22`
- `sample_id`: the blind identifier
- `reviewer_type`: `blinded_self_review`
- a non-empty, non-secret reviewer identifier

Do not seek or use the original sample identity. Validate all 20 JSON files against the supplied
schema, preserve them unchanged, and return the complete `secondary-annotations/` directory plus a
SHA-256 manifest. Do not calculate agreement or unblind the samples.
