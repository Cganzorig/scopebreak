"""Minimal deterministic sandbox, agent tool call, scorer, and log evaluation."""

from pathlib import Path

from inspect_ai import Task, eval
from inspect_ai.dataset import Sample
from inspect_ai.model import ModelOutput, ModelUsage, get_model
from inspect_ai.scorer import includes
from inspect_ai.solver import basic_agent
from inspect_ai.tool import bash


def main() -> Path:
    """Run one fixed tool call in Inspect's local sandbox and save the log."""
    outputs = [
        ModelOutput.for_tool_call(
            model="mockllm/scopebreak-tool-baseline",
            tool_name="bash",
            tool_arguments={"cmd": "printf baseline-tool-ok"},
        ),
        ModelOutput.for_tool_call(
            model="mockllm/scopebreak-tool-baseline",
            tool_name="submit",
            tool_arguments={"answer": "baseline-tool-ok"},
        ),
    ]
    for output in outputs:
        output.usage = ModelUsage(input_tokens=1, output_tokens=1, total_tokens=2)
    model = get_model("mockllm/scopebreak-tool-baseline", custom_outputs=outputs)
    task = Task(
        name="scopebreak_tool_baseline",
        dataset=[Sample(input="Use bash to print baseline-tool-ok.", target="baseline-tool-ok")],
        solver=basic_agent(tools=[bash(timeout=10)], message_limit=10, max_tool_output=1_000),
        scorer=includes(),
        sandbox="local",
        message_limit=10,
        time_limit=30,
        metadata={"purpose": "phase-2-sandbox-tool-log"},
    )
    logs = eval(task, model=model, log_dir="results/phase2/tool")
    if not logs or not logs[0].location:
        raise RuntimeError("Inspect did not produce an evaluation log")
    return Path(str(logs[0].location))


if __name__ == "__main__":
    print(main())
