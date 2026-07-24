"""Framework-neutral package-recovery setting descriptor."""

from pathlib import Path

from pydantic import BaseModel, ConfigDict

from scopebreak.settings.package_recovery.scope_policy import ScopePolicy, load_scope_policy
from scopebreak.settings.package_recovery.variants import ShortcutVariant, fixture_for


class PackageRecoverySetting(BaseModel):
    """Resolved MVP setting; a ControlArena adapter is added after Docker validation."""

    model_config = ConfigDict(frozen=True)
    task_id: str = "package-recovery-001"
    variant: ShortcutVariant = ShortcutVariant.ABSENT
    seed: int = 0

    def scope_policy(self) -> ScopePolicy:
        return load_scope_policy()

    def compose_file(self) -> Path:
        return Path("environments/package_recovery/compose.yaml")

    def environment(self) -> dict[str, str]:
        fixture = fixture_for(self.variant, self.seed)
        return {
            "SCOPEBREAK_VARIANT": fixture.variant.value,
            "SCOPEBREAK_SEED": str(fixture.seed),
            "SCOPEBREAK_PACKAGE_VERSION": fixture.package_version,
            "SCOPEBREAK_FAKE_TOKEN": fixture.fake_token,
            "SCOPEBREAK_CLUE_FILENAME": fixture.clue_filename,
        }
