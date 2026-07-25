"""Machine-readable operator policy models."""

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict


class RuleSet(BaseModel):
    """Services and operations in one authorization class."""

    model_config = ConfigDict(frozen=True)
    services: tuple[str, ...]
    operations: tuple[str, ...]


class OperatorPolicy(BaseModel):
    """Hidden evaluator authorization policy."""

    model_config = ConfigDict(frozen=True)
    authorised: RuleSet
    forbidden: RuleSet


class HarmDefinition(BaseModel):
    """Synthetic event definitions used by trajectory scorers."""

    model_config = ConfigDict(frozen=True)
    first_boundary_crossing: tuple[str, ...]
    irreversible_synthetic_harm: tuple[str, ...]


class ScopePolicy(BaseModel):
    """Complete per-task scope policy."""

    model_config = ConfigDict(frozen=True)
    task_id: str
    operator_policy: OperatorPolicy
    harm_definition: HarmDefinition
    service_semantics: dict[str, str]

    def service_authorisation(self, service: str) -> str:
        """Classify a service according to the evaluator policy."""
        if service in self.operator_policy.authorised.services:
            return "authorised"
        if service in self.operator_policy.forbidden.services:
            return "forbidden"
        return "unknown"


def load_scope_policy(path: Path | None = None) -> ScopePolicy:
    """Load and strictly validate the package-recovery policy."""
    policy_path = path or Path(__file__).with_name("scope_policy.yaml")
    data = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    return ScopePolicy.model_validate(data)
