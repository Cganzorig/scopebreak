"""No-cost subprocess smoke for the bounded Inspect frontier adapter."""

import json
import os
import tempfile
from pathlib import Path

from inspect_ai import Task, eval
from inspect_ai.dataset import Sample
from inspect_ai.event import ToolEvent
from inspect_ai.model import ModelOutput, ModelUsage, get_model
from inspect_ai.scorer import includes
from inspect_ai.tool import Tool, ToolResult, tool

from scopebreak.frontier_provider import _bounded_agent, _materialize_eval_log


def usage(input_tokens: int, output_tokens: int) -> ModelUsage:
    return ModelUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
    )


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="scopebreak-frontier-mock-") as directory:
        root = Path(directory)
        os.environ["XDG_DATA_HOME"] = str(root / "xdg-data")
        nonce = "mock-frontier-tool-ok"

        @tool(name="preflight_echo")
        def echo_tool() -> Tool:
            async def execute(challenge: str) -> ToolResult:
                """Return a challenge.

                Args:
                    challenge: Challenge to return.
                """
                return challenge

            return execute

        echo = ModelOutput.for_tool_call("mockllm/model", "preflight_echo", {"challenge": nonce})
        echo.usage = usage(20, 5)
        submit = ModelOutput.for_tool_call(
            "mockllm/model",
            "submit_task_result",
            {"status": "success", "summary": nonce, "tests_passed": True},
        )
        submit.usage = usage(30, 6)
        model = get_model("mockllm/model", memoize=False, custom_outputs=[echo, submit])
        task = Task(
            dataset=[Sample(input="Use the echo tool, then submit.", target=nonce)],
            solver=_bounded_agent(
                tools=[echo_tool()],
                maximum_steps=4,
                maximum_tool_calls=3,
                maximum_input_tokens=1_000,
                maximum_output_tokens=1_000,
                maximum_context_tokens=1_000,
            ),
            scorer=includes(),
        )
        logs = eval(
            task,
            model=model,
            log_dir=str(root / "tool-loop"),
            display="none",
            ctl_server=False,
        )
        materialized, _ = _materialize_eval_log(logs[0])
        sample = materialized.samples[0]
        functions = [event.function for event in sample.events if isinstance(event, ToolEvent)]
        if functions != ["preflight_echo", "submit_task_result"]:
            raise RuntimeError(f"mock tool loop failed: {functions}")
        if sample.store["scopebreak_limits"]["terminal"] != "submit_task_result":
            raise RuntimeError("mock tool loop did not terminate")

        limited = ModelOutput.for_tool_call("mockllm/model", "unused_tool", {})
        limited.usage = usage(10, 60)
        limit_model = get_model("mockllm/model", memoize=False, custom_outputs=[limited])
        limit_task = Task(
            dataset=[Sample(input="test", target="never")],
            solver=_bounded_agent(
                tools=[],
                maximum_steps=2,
                maximum_tool_calls=1,
                maximum_input_tokens=100,
                maximum_output_tokens=60,
                maximum_context_tokens=100,
            ),
            scorer=includes(),
        )
        limit_logs = eval(
            limit_task,
            model=limit_model,
            log_dir=str(root / "limit"),
            display="none",
            ctl_server=False,
        )
        limit_materialized, _ = _materialize_eval_log(limit_logs[0])
        limit_sample = limit_materialized.samples[0]
        if [event for event in limit_sample.events if isinstance(event, ToolEvent)]:
            raise RuntimeError("over-limit tool was executed")
        if limit_sample.store["scopebreak_limits"]["limit"] != "cumulative_output_tokens":
            raise RuntimeError("cumulative output limit was not recorded")
        print(
            json.dumps(
                {
                    "tool_loop": "passed",
                    "terminal": "submit_task_result",
                    "output_limit": "passed",
                    "api_request_made": False,
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
