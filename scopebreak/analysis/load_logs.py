"""Load normalized trajectory records from SCOPEBREAK JSON reports."""

import json
from pathlib import Path
from typing import Any

Record = dict[str, Any]


def _report_paths(path: Path) -> tuple[Path, ...]:
    if path.is_file():
        return (path,)
    direct = path / "report.json"
    if direct.is_file():
        return (direct,)
    return tuple(sorted(path.rglob("report.json")))


def load_records(path: Path) -> list[Record]:
    """Load all trajectory records below a result file or directory."""
    report_paths = _report_paths(path)
    if not report_paths:
        raise FileNotFoundError(f"no report.json found below {path}")
    records: list[Record] = []
    for report_path in report_paths:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
        report_records = payload.get("records")
        if not isinstance(report_records, list):
            raise ValueError(f"report has no records list: {report_path}")
        for record in report_records:
            if not isinstance(record, dict):
                raise ValueError(f"non-object record in {report_path}")
            records.append(record)
    return records
