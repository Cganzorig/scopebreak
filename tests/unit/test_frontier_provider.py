import json
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from inspect_ai.event import ModelEvent, ToolEvent
from inspect_ai.model import GenerateConfig, ModelOutput, ModelUsage

from scopebreak.frontier_provider import (
    ProviderRunResult,
    UsageSummary,
    _inspect_result,
    _resolved_model_is_requested_snapshot,
    _scan_for_credential,
    _usage_from_sample,
    save_provider_receipt,
    validate_provider_receipt,
)
from scopebreak.frontier_study import load_manifest

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

