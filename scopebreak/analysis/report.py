"""Generate machine-readable and concise Markdown analysis reports."""

import argparse
import json
from pathlib import Path
from typing import Any

from scopebreak.analysis.load_logs import load_records
from scopebreak.analysis.metrics import summarize_records


def _rate_line(label: str, value: dict[str, Any]) -> str:
    return (
        f"- {label}: {value['count']}/{value['total']} "
        f"({value['rate']:.1%}; Wilson 95% CI "
        f"{value['wilson_95_low']:.1%}-{value['wilson_95_high']:.1%})"
    )


def render_markdown(summary: dict[str, Any], *, scripted: bool) -> str:
    """Render a report without overstating deterministic instrumentation runs."""
    lines = ["# SCOPEBREAK analysis", ""]
    if scripted:
        lines.extend(
            [
                "> Scripted trajectories validate instrumentation only; they are not "
                "model-behaviour evidence.",
                "",
            ]
        )
    lines.extend(
        [
            f"Trajectories: {summary['trajectory_count']}",
            "",
            "## Primary outcomes",
            "",
            _rate_line("Task success", summary["task_success"]),
            _rate_line("Operator-policy violation", summary["operator_policy_violation"]),
            "",
            "## Escalation funnel",
            "",
        ]
    )
    lines.extend(
        f"- Stage {stage} or higher: {summary['escalation_funnel'][f'stage_{stage}_or_higher']}"
        for stage in range(1, 9)
    )
    lines.extend(["", "## Boundary conditions", ""])
    for boundary, metrics in summary["by_boundary_condition"].items():
        lines.append(f"### {boundary}")
        lines.append("")
        lines.append(_rate_line("Task success", metrics["task_success"]))
        lines.append(
            _rate_line("Operator-policy violation", metrics["operator_policy_violation"])
        )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def generate(input_path: Path, output_dir: Path) -> tuple[Path, Path]:
    """Load records and write JSON plus Markdown reports."""
    records = load_records(input_path)
    summary = summarize_records(records)
    scripted = all("scripted_behaviour" in record for record in records)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "analysis.json"
    markdown_path = output_dir / "analysis.md"
    json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    markdown_path.write_text(render_markdown(summary, scripted=scripted), encoding="utf-8")
    return json_path, markdown_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, default=Path("results/analysis"))
    args = parser.parse_args()
    print(*generate(args.input, args.output), sep="\n")


if __name__ == "__main__":
    main()
