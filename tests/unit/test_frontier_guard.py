from pathlib import Path

from scopebreak.frontier_guard import load_config, status

CONFIG = Path("configs/frontier_feasibility.example.yaml")


def test_frontier_guard_is_disabled_and_bounded(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    config = load_config(CONFIG)
    assert config["max_samples"] == 10
    assert config["estimated_upper_cost_usd"] <= config["max_cost_usd"]
    assert status(config, False)["state"] == "DRY_RUN"
    assert status(config, True)["state"] == "BLOCKED_CREDENTIALS_UNAVAILABLE"
