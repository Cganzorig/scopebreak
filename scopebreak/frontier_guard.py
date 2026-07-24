"""Cost, sample, credential, and confirmation gate for frontier evaluation."""

import argparse
import json
import os
from pathlib import Path
from typing import Any

import yaml


def load_config(path: Path) -> dict[str, Any]:
    config: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    expected_samples = len(config["boundary_conditions"]) * config["samples_per_condition"]
    if expected_samples != config["max_samples"]:
        raise ValueError("condition sample count must exactly equal max_samples")
    if config["estimated_upper_cost_usd"] > config["max_cost_usd"]:
        raise ValueError("estimated upper cost exceeds configured maximum")
    if config["monitor"]["mode"] != "observe_only":
        raise ValueError("feasibility gate must use an observe-only monitor")
    return config


def status(config: dict[str, Any], execute: bool) -> dict[str, Any]:
    credential_name = "OPENAI_API_KEY" if config["provider"] == "openai" else ""
    credential_available = bool(credential_name and os.getenv(credential_name))
    confirmation_matches = (
        os.getenv("SCOPEBREAK_FRONTIER_CONFIRM") == config["confirmation_phrase"]
    )
    state = "DRY_RUN"
    if execute and not credential_available:
        state = "BLOCKED_CREDENTIALS_UNAVAILABLE"
    elif execute and not config["enabled"]:
        state = "BLOCKED_CONFIG_DISABLED"
    elif execute and not confirmation_matches:
        state = "BLOCKED_CONFIRMATION_REQUIRED"
    elif execute:
        state = "READY"
    return {
        "state": state,
        "model": config["model"],
        "samples": config["max_samples"],
        "maximum_input_tokens": config["max_input_tokens_per_sample"],
        "maximum_output_tokens": config["max_output_tokens_per_sample"],
        "estimated_upper_cost_usd": config["estimated_upper_cost_usd"],
        "maximum_cost_usd": config["max_cost_usd"],
        "credential_available": credential_available,
        "confirmation_required": config["confirmation_phrase"],
        "monitor_mode": config["monitor"]["mode"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/frontier_feasibility.example.yaml"),
    )
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    result = status(load_config(args.config), args.execute)
    print(json.dumps(result, indent=2))
    if args.execute and result["state"] != "READY":
        raise SystemExit(2)
    if args.execute and result["state"] == "READY":
        raise SystemExit(
            "Frontier adapter is intentionally not armed in the example configuration. "
            "Save a non-example reviewed config before execution."
        )


if __name__ == "__main__":
    main()
