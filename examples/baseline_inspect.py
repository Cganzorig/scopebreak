"""Small official-pattern Inspect evaluation requiring no external model."""

from pathlib import Path

from inspect_ai import Task, eval
from inspect_ai.dataset import Sample
from inspect_ai.model import ModelOutput, ModelUsage, get_model
from inspect_ai.scorer import includes
from inspect_ai.solver import generate


def main() -> Path:
    """Run the documented Task/Sample/generate/scorer pattern with MockLLM."""
    output = ModelOutput.from_content("mockllm/scopebreak-baseline", "baseline-ok")
    output.usage = ModelUsage(input_tokens=1, output_tokens=1, total_tokens=2)
    task = Task(
        name="scopebreak_official_pattern",
        dataset=[Sample(input="Respond with exactly: baseline-ok", target="baseline-ok")],
        solver=generate(),
        scorer=includes(),
        message_limit=2,
        time_limit=30,
        metadata={"purpose": "phase-2-official-pattern"},
    )
    model = get_model(
        "mockllm/scopebreak-baseline",
        custom_outputs=[output],
    )
    logs = eval(task, model=model, log_dir="results/phase2/official")
    if not logs or not logs[0].location:
        raise RuntimeError("Inspect did not produce an evaluation log")
    return Path(str(logs[0].location))


if __name__ == "__main__":
    print(main())
