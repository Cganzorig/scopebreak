"""Run and verify the Phase 2 baseline evaluations."""

import os
from pathlib import Path

# Keep Inspect traces inside the experiment workspace. This also makes the
# command work in managed hosts where the user's home directory is read-only.
os.environ.setdefault("XDG_DATA_HOME", str(Path("results/.local-share").resolve()))

from control_arena.eval import ControlEvalConfig, get_control_task
from control_arena.settings import Setting
from inspect_ai.log import read_eval_log

from examples.baseline_inspect import main as run_official_pattern
from examples.baseline_tool_eval import main as run_tool_baseline


def main() -> None:
    official_log = read_eval_log(str(run_official_pattern()))
    tool_log = read_eval_log(str(run_tool_baseline()))

    assert official_log.status == "success"
    assert official_log.samples and official_log.samples[0].scores
    assert tool_log.status == "success"
    assert tool_log.samples and tool_log.samples[0].scores
    sample = tool_log.samples[0]
    scores = sample.scores
    assert scores is not None
    assert all(str(score.value) in {"C", "1", "1.0"} for score in scores.values())
    assert any(message.role == "tool" for message in sample.messages)
    assert any(getattr(message, "tool_calls", None) for message in sample.messages)

    # These imports are the current ControlArena entry points that the custom
    # setting will implement in Phase 3. Referencing them makes API drift fail
    # immediately without loading a benchmark dataset or contacting a model.
    assert ControlEvalConfig is not None
    assert get_control_task is not None
    assert Setting is not None
    print(f"official_log={official_log.location}")
    print(f"tool_log={tool_log.location}")
    print("control_arena_import=ok")


if __name__ == "__main__":
    main()
