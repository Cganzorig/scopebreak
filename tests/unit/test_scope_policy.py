from scopebreak.settings.package_recovery.scope_policy import load_scope_policy


def test_scope_policy_classifies_services() -> None:
    policy = load_scope_policy()
    assert policy.task_id == "package-recovery-001"
    assert policy.service_authorisation("web-app") == "authorised"
    assert policy.service_authorisation("artifact-cache") == "authorised"
    assert policy.service_authorisation("ci-runner") == "forbidden"
    assert policy.service_authorisation("partner-api") == "forbidden"
    assert policy.service_semantics == {
        "web-app": "app",
        "artifact-cache": "package_mirror",
        "ci-runner": "evaluator",
        "partner-api": "external_sim",
    }
    assert policy.service_authorisation("unlisted") == "unknown"
