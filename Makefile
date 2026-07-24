UV := UV_CACHE_DIR=/tmp/scopebreak-uv-cache UV_PYTHON_INSTALL_DIR=.uv-python /home/ubuntu/.local/bin/uv

.PHONY: bootstrap verify test lint safety-test smoke-mock frontier-feasibility model-start smoke-local pilot-local analyse clean-sandboxes

bootstrap:
	$(UV) sync --frozen

verify:
	bash scripts/verify_host.sh

test:
	$(UV) run pytest

lint:
	$(UV) run ruff check .
	$(UV) run mypy scopebreak

safety-test:
	$(UV) run pytest tests/safety

smoke-mock:
	bash scripts/run_mock_smoke.sh

frontier-feasibility:
	bash scripts/run_frontier_feasibility.sh

model-start:
	bash scripts/start_model.sh

smoke-local:
	bash scripts/run_local_smoke.sh

pilot-local:
	bash scripts/run_local_pilot.sh

analyse:
	bash scripts/analyse.sh

clean-sandboxes:
	bash scripts/clean_sandboxes.sh
