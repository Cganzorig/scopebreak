"""One bounded local-model Inspect trajectory with a real Bash tool call."""

from pathlib import Path

from inspect_ai import Task, eval
from inspect_ai.dataset import Sample
from inspect_ai.model import GenerateConfig, get_model
from inspect_ai.scorer import includes
from inspect_ai.solver import basic_agent
from inspect_ai.tool import bash


def main() -> Path:
    """Run and validate one local Qwen3 tool-using trajectory."""
    model = get_model(
        "vllm/scopebreak-qwen3-8b",
        base_url="http://127.0.0.1:8000/v1",
        config=GenerateConfig(temperature=0.0, max_tokens=512),
    )
    task = Task(
        name="scopebreak_local_tool_smoke",
        dataset=[
            Sample(
                input=(
                    "Call the bash tool exactly once, using its `cmd` argument with the "
                    "value `printf local-tool-ok`. Then call submit with exactly "
                    "`local-tool-ok`."
                ),
                target="local-tool-ok",
            )
        ],
        solver=basic_agent(
            tools=[bash(timeout=10)],
            message_limit=8,
            max_tool_output=1_000,
        ),
        scorer=includes(),
        sandbox="local",
        message_limit=8,
        time_limit=120,
        metadata={
            "purpose": "bounded-a10-local-model-tool-call-smoke",
            "model_role": "pipeline-validation-only",
        },
    )
    logs = eval(task, model=model, log_dir="results/local-smoke")
    if not logs or not logs[0].location:
        raise RuntimeError("Inspect did not produce a local-model evaluation log")
    if logs[0].status != "success":
        raise RuntimeError(f"local-model evaluation failed: {logs[0].status}")
    results = logs[0].results
    if results is None or not results.scores:
        raise RuntimeError("local-model evaluation produced no aggregate score")
    accuracy = results.scores[0].metrics.get("accuracy")
    if accuracy is None or accuracy.value != 1.0:
        raise RuntimeError("local model did not complete the tool trajectory correctly")
    return Path(str(logs[0].location))


if __name__ == "__main__":
    print(main())
