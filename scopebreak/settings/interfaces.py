"""Shared setting interfaces independent of framework adapters."""

from pathlib import Path
from typing import Protocol

from scopebreak.settings.package_recovery.scope_policy import ScopePolicy


class ScopebreakSetting(Protocol):
    """Minimum interface required by scorers and environment runners."""

    task_id: str

    def scope_policy(self) -> ScopePolicy: ...

    def compose_file(self) -> Path: ...
