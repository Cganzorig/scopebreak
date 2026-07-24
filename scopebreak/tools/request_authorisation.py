"""Safe action for requesting operator authorization."""

from pydantic import BaseModel, ConfigDict, Field


class AuthorisationRequest(BaseModel):
    """Recorded authorization request; the MVP denies by default."""

    model_config = ConfigDict(frozen=True)
    resource: str = Field(min_length=1)
    proposed_action: str = Field(min_length=1)
    justification: str = Field(min_length=1)
    decision: str = "denied"


def request_authorisation(
    resource: str, proposed_action: str, justification: str
) -> AuthorisationRequest:
    """Record a safe authorization request and default denial."""
    return AuthorisationRequest(
        resource=resource,
        proposed_action=proposed_action,
        justification=justification,
    )
