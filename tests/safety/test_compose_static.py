from pathlib import Path

import yaml

ENVIRONMENT = Path("environments/package_recovery")


def compose() -> dict[str, object]:
    return yaml.safe_load((ENVIRONMENT / "compose.yaml").read_text(encoding="utf-8"))


def test_all_networks_are_internal() -> None:
    networks = compose()["networks"]
    assert isinstance(networks, dict)
    assert networks
    assert all(config.get("internal") is True for config in networks.values())


def test_services_are_unprivileged_without_dangerous_mounts() -> None:
    services = compose()["services"]
    assert isinstance(services, dict)
    for name, service in services.items():
        assert service.get("privileged", False) is False, name
        assert service.get("read_only") is True, name
        assert "ALL" in service.get("cap_drop", []), name
        mounts = str(service.get("volumes", []))
        assert "/var/run/docker.sock" not in mounts, name
        assert "':/'" not in mounts and " -> /" not in mounts, name


def test_no_public_ports_are_published() -> None:
    services = compose()["services"]
    assert isinstance(services, dict)
    assert all("ports" not in service for service in services.values())


def test_fixtures_contain_only_manifestly_fake_secrets_and_domains() -> None:
    fixture_files = [
        *ENVIRONMENT.rglob("*.py"),
        *ENVIRONMENT.rglob("Dockerfile"),
        *ENVIRONMENT.rglob("*.yaml"),
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in fixture_files)
    forbidden_secret_prefixes = ("AKIA", "ghp_", "github_pat_", "sk-proj-", "xoxb-")
    assert not any(prefix in combined for prefix in forbidden_secret_prefixes)
    assert ".com" not in combined and ".net" not in combined and ".org" not in combined
