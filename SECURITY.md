# Security policy

## Scope

SCOPEBREAK is a synthetic research harness, not a production security boundary.
Do not connect its evaluator, simulated external service, synthetic credentials,
or attack controls to real systems or secrets.

Security-relevant issues include real credential material committed to the
repository, unexpected public or metadata-network access from an experiment
container, writable host or Docker-socket exposure, evaluator integrity bypass,
or cleanup behavior that leaves reachable services running.

## Reporting

Use GitHub's private vulnerability-reporting or security-advisory feature for
this repository. If that feature is unavailable, contact the repository owner
through a private channel before disclosing details. Do not place credentials,
private endpoints, exploit details, or sensitive logs in a public issue.

Reports should include the affected commit, environment, reproduction steps,
expected containment boundary, observed behavior, and any evidence that a real
secret or external target was involved. Revoke an exposed credential before
waiting for repository remediation.

Ordinary documentation errors, clearly synthetic fixture values, and research-
methodology questions may be reported through public issues.
