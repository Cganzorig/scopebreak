from scopebreak.tools.report_blocker import report_blocker
from scopebreak.tools.request_authorisation import request_authorisation
from scopebreak.tools.submit_task_result import CompletionStatus, submit_task_result


def test_safe_actions_are_structured() -> None:
    request = request_authorisation(
        "evaluator", "inspect tests", "authorised route appears blocked"
    )
    assert request.decision == "denied"
    report = report_blocker(
        "mirror unavailable", ["checked logs"], "ask operator to inspect mirror"
    )
    assert report.attempted_steps == ("checked logs",)
    result = submit_task_result(CompletionStatus.BLOCKED, "Stopped safely")
    assert result.status is CompletionStatus.BLOCKED
