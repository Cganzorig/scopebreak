import json
from pathlib import Path

from scopebreak.mock_eval import run
from scopebreak.telemetry.parser import load_jsonl


def test_mock_matrix_generates_parseable_report_and_telemetry(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    source = Path(__file__).parents[2] / "configs" / "smoke.yaml"
    report_path = run(source)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["trajectory_count"] == 36
    telemetry_files = sorted((tmp_path / "results/mock-smoke/telemetry").glob("*.jsonl"))
    assert len(telemetry_files) == 36
    assert all(load_jsonl(path) for path in telemetry_files)
    absent_escalation = [
        record
        for record in report["records"]
        if record["variant"] == "A" and record["scripted_behaviour"] == "escalation"
    ]
    assert absent_escalation
    assert all(record["maximum_stage"] == 3 for record in absent_escalation)
