"""Discover profile files on disk.

Lookup is by profile id. If two files declare the same id the one with the
higher schema version wins; otherwise, alphabetical. Directory can be
overridden with BIMGUARD_PROFILES_DIR (used by tests).
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from app.engines.profiles.loader import ProfileLoadError, load_from_file
from app.engines.profiles.types import Profile

log = logging.getLogger("bimguard.profiles")

_API_DIR = Path(__file__).resolve().parents[3]  # apps/api
_DEFAULT_DIR = _API_DIR / "data" / "profiles"


def default_dir() -> Path:
    override = os.environ.get("BIMGUARD_PROFILES_DIR")
    return Path(override) if override else _DEFAULT_DIR


def _files(directory: Path) -> list[Path]:
    if not directory.exists():
        return []
    return sorted([*directory.glob("*.yaml"), *directory.glob("*.yml")])


def list_profiles(directory: Path | None = None) -> list[Profile]:
    """Return every valid profile. Invalid files are skipped and logged."""
    directory = directory or default_dir()
    out: list[Profile] = []
    for path in _files(directory):
        try:
            out.append(load_from_file(path))
        except ProfileLoadError as exc:
            log.warning("Skipping invalid profile %s: %s", path.name, exc)
    return sorted(out, key=lambda p: p.id)


def load_by_id(profile_id: str, directory: Path | None = None) -> Profile | None:
    for profile in list_profiles(directory):
        if profile.id == profile_id:
            return profile
    return None


def load_with_errors(directory: Path | None = None) -> list[tuple[str, Profile | None, str | None]]:
    """Return (filename, profile, error) for every file, valid or not."""
    directory = directory or default_dir()
    out: list[tuple[str, Profile | None, str | None]] = []
    for path in _files(directory):
        try:
            out.append((path.name, load_from_file(path), None))
        except ProfileLoadError as exc:
            out.append((path.name, None, str(exc)))
    return out