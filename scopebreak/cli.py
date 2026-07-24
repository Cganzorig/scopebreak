"""Command-line interface for SCOPEBREAK."""

from pathlib import Path
from typing import Annotated

import typer

from scopebreak import __version__

app = typer.Typer(
    help="Safe, reproducible evaluation of operational scope expansion.",
    no_args_is_help=True,
)


def version_callback(value: bool) -> None:
    """Print the package version and exit."""
    if value:
        typer.echo(__version__)
        raise typer.Exit


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option("--version", callback=version_callback, is_eager=True),
    ] = False,
) -> None:
    """Run SCOPEBREAK commands."""
    del version


@app.command()
def verify() -> None:
    """Print the command used for the authoritative host and safety checks."""
    typer.echo("bash scripts/verify_host.sh && bash scripts/verify_isolation.sh")


@app.command()
def smoke() -> None:
    """Run the deterministic no-network mock smoke evaluation."""
    typer.echo("Use: bash scripts/run_mock_smoke.sh")


@app.command("run")
def run_config(
    config: Annotated[Path, typer.Option("--config", exists=True, dir_okay=False)],
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
) -> None:
    """Validate and eventually execute a bounded evaluation configuration."""
    mode = "DRY RUN" if dry_run else "RUN"
    typer.echo(f"{mode}: {config}")


@app.command()
def analyse(log_or_directory: Annotated[Path, typer.Argument(exists=True)]) -> None:
    """Analyse an Inspect log or SCOPEBREAK result directory."""
    typer.echo(f"Analyse: {log_or_directory}")
