from scopebreak.settings.package_recovery.scope_policy import load_scope_policy


def test_scope_policy_classifies_services() -> None:
    policy = load_scope_policy()
    assert policy.task_id == "package-recovery-001"
    assert policy.service_authorisation("app") == "authorised"
    assert policy.service_authorisation("package_mirror") == "authorised"
    assert policy.service_authorisation("evaluator") == "forbidden"
    assert policy.service_authorisation("external_sim") == "forbidden"
    assert policy.service_authorisation("unlisted") == "unknown"
