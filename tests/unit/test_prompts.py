from scopebreak.agents.prompts import BoundaryCondition, task_prompt


def test_scope_silent_prompt_does_not_leak_planted_boundary() -> None:
    prompt = task_prompt(BoundaryCondition.SILENT).lower()
    for leaked_term in ("evaluator", "external_sim", "shortcut", "credential", "forbidden"):
        assert leaked_term not in prompt


def test_explicit_prompt_directly_communicates_boundary() -> None:
    prompt = task_prompt(BoundaryCondition.EXPLICIT).lower()
    assert "evaluator infrastructure" in prompt
    assert "outside your authorised scope" in prompt
    assert "do not access" in prompt
