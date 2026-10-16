"""Load and validate a profile from disk or from a plain dict.

Every failure raises ProfileLoadError with a message safe to show a user.
No partial profile is ever returned: either the whole file is valid, or
nothing loads.
"""
from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from app.engines.profiles.types import Profile
from app.engines.validation import validate_configuration


class ProfileLoadError(Exception):
    """Raised when a profile file cannot be loaded or fails validation."""


def load_from_file(path: Path) -> Profile:
    if not path.exists():
        raise ProfileLoadError(f"Profile file not found: {path}")
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ProfileLoadError(f"Cannot read {path.name}: {exc}") from exc
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ProfileLoadError(f"Invalid YAML in {path.name}: {exc}") from exc
    if not isinstance(data, dict):
        raise ProfileLoadError(f"Profile {path.name} must be a YAML mapping.")
    return load_from_dict(data, source=path.name)


def load_from_dict(data: dict, source: str = "<dict>") -> Profile:
    try:
        profile = Profile.model_validate(data)
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in exc.errors()
        )
        raise ProfileLoadError(f"Invalid profile {source}: {problems}") from exc

    for rule_id, override in profile.rules.items():
        try:
            validate_configuration(rule_id, override.severity, override.params)
        except ValueError as exc:
            raise ProfileLoadError(f"Invalid rule {rule_id} in {source}: {exc}") from exc
    return profile