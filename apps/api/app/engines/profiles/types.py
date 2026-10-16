"""Pydantic models for a quality profile.

A profile is a named, versioned bundle of rule overrides. It does not add
new rules; it configures the rules that already exist in the engine. That
keeps profiles reviewable and makes the effect of activating one purely a
configuration change.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.engines.validation import BY_ID


class ProfileRuleOverride(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool | None = None
    severity: str | None = None
    params: dict | None = None


class Profile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: int = Field(default=1, ge=1)
    id: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9-]*$")
    name: str = Field(min_length=1, max_length=255)
    description: str = ""
    illustrative: bool = True
    rules: dict[str, ProfileRuleOverride] = Field(default_factory=dict)

    @field_validator("rules")
    @classmethod
    def _known_rule_ids(cls, v: dict[str, ProfileRuleOverride]) -> dict[str, ProfileRuleOverride]:
        unknown = set(v) - set(BY_ID)
        if unknown:
            raise ValueError(f"Unknown rule id(s): {', '.join(sorted(unknown))}.")
        return v