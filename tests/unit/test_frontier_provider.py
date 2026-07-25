import asyncio
import json
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from inspect_ai.event import ModelEvent, ToolEvent
from inspect_ai.model import GenerateConfig, ModelOutput, ModelUsage
from inspect_ai.tool._tool_info import parse_tool_info

from scopebreak.agents.prompts import BoundaryCondition
from scopebreak.frontier_provider import (
    PackageRecoveryEnvironment,
    ProviderRunResult,
    UsageSummary,
    _inspect_result,
    _resolved_model_is_requested_snapshot,
    _scan_for_credential,
    _usage_from_sample,
    _worker_shell_tool,
    save_provider_receipt,
    validate_provider_receipt,
)
from scopebreak.frontier_study import load_manifest
from scopebreak.settings.package_recovery.variants import ShortcutVariant

MANIFEST = Path("configs/frontier-study-v1.yaml")


def _usage(input_tokens: int = 20, output_tokens: int = 5) -> ModelUsage:
    return ModelUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
    )


def _result() -> ProviderRunResult:
    return ProviderRunResult(
        phase="preflight",
        requested_model="gpt-5.6-sol",
        resolved_model="gpt-5.6-sol-2026-07-01",
        reasoning_effort="medium",
        temperature=0,
        inspect_log="inspect/test.eval",
        usage=UsageSummary(
            cumulative_input_tokens=40,
            cumulative_output_tokens=10,
            reasoning_tokens=2,
            peak_context_tokens=25,
            context_tokens_by_turn=(15, 25),
            provider_latency_seconds_by_turn=(0.1, 0.1),
            actual_cost_usd=0.0005,
            cost_source="frozen_manifest_uncached_rates",
        ),
        tool_call_verified=True,
        credential_validated=True,
        provider_terms_attested=True,
        tool_calls=2,
        steps=2,
        wall_clock_runtime_seconds=0.2,
        terminal_state_reached=True,
        terminal_reason="submit_task_result",
        task_success=True,
        meaningful_progress=True,
        cleanup_success=True,
        malformed_tool_calls=0,
        repeated_tool_calls=0,
    )


def test_model_resolution_allows_only_requested_model_or_snapshot() -> None:
    assert _resolved_model_is_requested_snapshot("gpt-5.6-sol", "gpt-5.6-sol")
    assert _resolved_model_is_requested_snapshot(
        "gpt-5.6-sol", "gpt-5.6-sol-2026-07-01"
    )
    assert not _resolved_model_is_requested_snapshot("gpt-5.6-sol", "gpt-5.6-terra")


def test_calibration_reuses_frozen_images_without_rebuilding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    environment = PackageRecoveryEnvironment("calibration-test", 149482140, tmp_path)
    host_calls: list[list[str]] = []
    compose_calls: list[list[str]] = []

    def host_docker(arguments: list[str], *, check: bool = True) -> SimpleNamespace:
        del check
        host_calls.append(arguments)
        return SimpleNamespace(returncode=0)

    def compose_run(
        arguments: list[str], *, timeout: int = 120, check: bool = True
    ) -> SimpleNamespace:
        del timeout, check
        compose_calls.append(arguments)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(environment, "_host_docker", host_docker)
    monkeypatch.setattr(environment, "_run", compose_run)
    digests = {
        "ops-worker": "sha256:ops",
        "web-app": "sha256:web",
        "artifact-cache": "sha256:cache",
    }
    environment.start(digests)

    assert ["image", "inspect", "sha256:ops"] in host_calls
    assert [
        "tag",
        "sha256:ops",
        f"{environment.project}-ops-worker:latest",
    ] in host_calls
    assert compose_calls == [["up", "-d", "--wait", "--no-build", "ops-worker"]]


def test_variant_c_uses_frozen_shortcut_images_and_overlay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    environment = PackageRecoveryEnvironment(
        "gate-c-test",
        7,
        tmp_path,
        variant=ShortcutVariant.DISCOVERABLE,
        boundary=BoundaryCondition.SILENT,
    )
    host_calls: list[list[str]] = []
    compose_calls: list[list[str]] = []

    def host_docker(arguments: list[str], *, check: bool = True) -> SimpleNamespace:
        del check
        host_calls.append(arguments)
        return SimpleNamespace(returncode=0)

    def compose_run(
        arguments: list[str], *, timeout: int = 120, check: bool = True
    ) -> SimpleNamespace:
        del timeout, check
        compose_calls.append(arguments)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(environment, "_host_docker", host_docker)
    monkeypatch.setattr(environment, "_run", compose_run)
    digests = {service: f"sha256:{service}" for service in environment.services}
    environment.start(digests)

    assert "environments/package_recovery/compose.shortcut.yaml" in environment.base
    assert ["image", "inspect", "sha256:ci-runner"] in host_calls
    assert ["image", "inspect", "sha256:partner-api"] in host_calls
    assert compose_calls == [
        [
            "up",
            "-d",
            "--wait",
            "--no-build",
            "ops-worker",
            "ci-runner",
            "partner-api",
        ]
    ]


def test_worker_shell_v11_accepts_bounded_timeout_argument() -> None:
    calls: list[tuple[str, int]] = []

    def handler(command: str, timeout_ms: int) -> str:
        calls.append((command, timeout_ms))
        return "ok"

    worker = _worker_shell_tool(handler)
    info = parse_tool_info(worker)

    assert set(info.parameters.properties) == {"command", "timeout_ms"}
    assert info.parameters.required == ["command"]
    assert info.parameters.properties["timeout_ms"].default == 30_000
    assert asyncio.run(worker(command="pytest -q", timeout_ms=20_000)) == "ok"
    assert calls == [("pytest -q", 20_000)]


@pytest.mark.parametrize("timeout_ms", [0, 999, 30_001])
def test_worker_shell_v11_rejects_out_of_range_timeout(timeout_ms: int) -> None:
    worker = _worker_shell_tool(lambda command, milliseconds: f"{command}:{milliseconds}")

    with pytest.raises(ValueError, match="between 1000 and 30000"):
        asyncio.run(worker(command="true", timeout_ms=timeout_ms))


def test_environment_worker_shell_uses_requested_bounded_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    environment = PackageRecoveryEnvironment("timeout-test", 7, tmp_path)
    observed: list[tuple[list[str], int]] = []

    def compose_run(
        arguments: list[str], *, timeout: int = 120, check: bool = True
    ) -> SimpleNamespace:
        del check
        observed.append((arguments, timeout))
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(environment, "_run", compose_run)

    assert environment.worker_shell("pytest -q", timeout_ms=20_000) == "ok"
    assert observed == [
        (["exec", "-T", "ops-worker", "sh", "-lc", "pytest -q"], 20)
    ]


def test_provider_receipt_is_checksum_bound_and_model_bound(tmp_path: Path) -> None:
    manifest = load_manifest(MANIFEST)
    receipt = save_provider_receipt(_result(), tmp_path, "commit")
    validated = validate_provider_receipt(
        receipt, phase="preflight", git_commit="commit", manifest=manifest
    )
    assert validated["tool_call_verified"] is True
    payload = json.loads(receipt.read_text(encoding="utf-8"))
    payload["resolved_model"] = "gpt-5.6-terra"
    receipt.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="checksum mismatch"):
        validate_provider_receipt(
            receipt, phase="preflight", git_commit="commit", manifest=manifest
        )


def test_credential_scan_reads_inside_inspect_zip(tmp_path: Path) -> None:
    credential = "sk-test-credential-value-123456789"
    archive = tmp_path / "trace.eval"
    with zipfile.ZipFile(archive, "w") as stream:
        stream.writestr("trace.json", f'{{"authorization": "{credential}"}}')
    assert _scan_for_credential(tmp_path, credential) is True


def _model_event(*, error: str | None = None, usage: bool = True) -> ModelEvent:
    output = ModelOutput.from_content(model="gpt-5.6-sol", content="test")
    output.usage = _usage() if usage else None
    return ModelEvent(
        model="openai/gpt-5.6-sol",
        input=[],
        tools=[],
        tool_choice="auto",
        config=GenerateConfig(reasoning_effort="medium", temperature=0),
        output=output,
        error=error,
    )


def test_missing_provider_usage_fails_closed() -> None:
    sample = SimpleNamespace(events=[_model_event(usage=False)])
    with pytest.raises(RuntimeError, match="usage metadata is missing"):
        _usage_from_sample(sample, 5, 30)


def test_inspect_limit_is_preserved_as_truncation_not_provider_failure(
    tmp_path: Path,
) -> None:
    sample = SimpleNamespace(
        error="sample time limit exceeded",
        events=[_model_event()],
        model_fallbacks=None,
        total_time=10.0,
        store={"scopebreak_limits": {"limit": "time"}},
        limit="time",
    )
    log = SimpleNamespace(status="error", samples=[sample])
    result = _inspect_result(
        phase="trajectory",
        requested_model="gpt-5.6-sol",
        manifest=load_manifest(MANIFEST),
        log=log,
        inspect_log=tmp_path / "test.eval",
        expected_tool=None,
        terminal_tools={"submit_task_result"},
        task_success=False,
        meaningful_progress=False,
        cleanup_success=True,
    )
    assert result.terminal_state_reached is False
    assert result.truncation_reason == "time"


@pytest.mark.parametrize(
    ("model_error", "fallback", "tool_failed", "expected"),
    [
        ("provider unavailable", False, False, "provider returned an error"),
        (None, True, False, "fallback detected"),
        (None, False, True, "required Inspect tool call did not succeed"),
    ],
)
def test_provider_error_fallback_and_malformed_tool_fail_closed(
    tmp_path: Path,
    model_error: str | None,
    fallback: bool,
    tool_failed: bool,
    expected: str,
) -> None:
    events: list[object] = [_model_event(error=model_error)]
    if tool_failed:
        events.append(
            ToolEvent(
                id="call",
                function="preflight_echo",
                arguments={"challenge": "x"},
                result="",
                failed=True,
            )
        )
    sample = SimpleNamespace(
        error=None,
        events=events,
        model_fallbacks=[object()] if fallback else None,
        total_time=0.1,
    )
    log = SimpleNamespace(status="success", samples=[sample])
    with pytest.raises(RuntimeError, match=expected):
        _inspect_result(
            phase="preflight",
            requested_model="gpt-5.6-sol",
            manifest=load_manifest(MANIFEST),
            log=log,
            inspect_log=tmp_path / "test.eval",
            expected_tool="preflight_echo",
            terminal_tools={"submit_task_result"},
            task_success=True,
            meaningful_progress=True,
            cleanup_success=True,
        )


def test_receipt_above_cost_limit_fails_closed(tmp_path: Path) -> None:
    manifest = load_manifest(MANIFEST)
    expensive_usage = _result().usage.model_copy(update={"actual_cost_usd": 2.0})
    expensive = _result().model_copy(update={"usage": expensive_usage})
    receipt = save_provider_receipt(expensive, tmp_path, "commit")
    with pytest.raises(ValueError, match="cost exceeds"):
        validate_provider_receipt(
            receipt, phase="preflight", git_commit="commit", manifest=manifest
        )
