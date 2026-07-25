from scopebreak.agents.prompts import BoundaryCondition, task_prompt


def test_scope_silent_prompt_does_not_leak_planted_boundary() -> None:
    prompt = task_prompt(BoundaryCondition.SILENT).lower()
    for leaked_term in (
        "evaluator",
        "external_sim",
        "shortcut",
        "credential",
        "forbidden",
        "monitor",
        "side task",
        "benchmark",
        "scopebreak",
    ):
        assert leaked_term not in prompt


def test_explicit_prompt_directly_communicates_boundary() -> None:
    prompt = task_prompt(BoundaryCondition.EXPLICIT).lower()
    assert "ci runners" in prompt
    assert "vendor-facing services" in prompt
    assert "outside your authorised scope" in prompt
    assert "do not access" in prompt
