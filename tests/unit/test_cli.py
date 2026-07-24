from typer.testing import CliRunner

from scopebreak.cli import app


def test_help_lists_required_commands() -> None:
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    for command in ("verify", "smoke", "run", "analyse"):
        assert command in result.stdout


def test_version() -> None:
    result = CliRunner().invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == "0.1.0"
