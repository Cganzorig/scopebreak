UV ?= uv
PYTHON := .venv/bin/python

.PHONY: bootstrap verify test lint safety-test smoke-mock frontier-dry-run frontier-mock frontier-preflight frontier-calibrate frontier-feasibility frontier-canary-review frontier-provider-recovery-review frontier-backup frontier-backup-check frontier-git-backup-check frontier-annotate-check frontier-agreement frontier-report model-bootstrap model-download model-start model-stop smoke-local pilot-local analyse clean-sandboxes

bootstrap:
	UV_CACHE_DIR=/tmp/scopebreak-uv-cache UV_PYTHON_INSTALL_DIR=.uv-python $(UV) sync --frozen

verify:
	bash scripts/verify_host.sh

test:
	.venv/bin/pytest

lint:
	.venv/bin/ruff check .
	.venv/bin/mypy scopebreak

safety-test:
	.venv/bin/pytest tests/safety

smoke-mock:
	bash scripts/run_mock_smoke.sh

frontier-feasibility:
	$(PYTHON) -m scopebreak.frontier_study execute

frontier-canary-review:
	$(PYTHON) -m scopebreak.frontier_study canary-review

frontier-provider-recovery-review:
	$(PYTHON) -m scopebreak.frontier_study provider-recovery-review

frontier-dry-run:
	$(PYTHON) -m scopebreak.frontier_study dry-run

frontier-mock:
	$(PYTHON) -m pytest tests/unit/test_frontier_provider.py tests/unit/test_frontier_study.py tests/unit/test_frontier_gate.py
	$(PYTHON) scripts/run_frontier_provider_mock.py

frontier-preflight:
	$(PYTHON) -m scopebreak.frontier_study preflight

frontier-calibrate:
	$(PYTHON) -m scopebreak.frontier_study calibrate

frontier-backup:
	$(PYTHON) -m scopebreak.frontier_study backup

frontier-backup-check:
	$(PYTHON) -m scopebreak.frontier_study backup-check

frontier-git-backup-check:
	$(PYTHON) -m scopebreak.frontier_study git-backup-check

frontier-annotate-check:
	$(PYTHON) -m scopebreak.frontier_study annotate-check

frontier-agreement:
	$(PYTHON) -m scopebreak.frontier_study agreement

frontier-report:
	$(PYTHON) -m scopebreak.frontier_study report

model-bootstrap:
	bash scripts/bootstrap_model_env.sh

model-download:
	bash scripts/download_model.sh

model-start:
	bash scripts/start_model.sh

model-stop:
	bash scripts/stop_model.sh

smoke-local:
	bash scripts/run_local_smoke_managed.sh

pilot-local:
	bash scripts/run_local_pilot.sh

analyse:
	bash scripts/analyse.sh

clean-sandboxes:
	bash scripts/clean_sandboxes.sh
