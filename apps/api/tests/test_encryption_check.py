"""Tests for the encryption declaration startup check (M24)."""
import logging

import pytest

from app.core.config import get_settings
from app.core.security import ensure_encryption_declared


def _set(monkeypatch, *, environment, encryption_mode):
    s = get_settings()
    monkeypatch.setattr(s, "environment", environment)
    monkeypatch.setattr(s, "encryption_mode", encryption_mode)


def test_dev_with_none_passes(monkeypatch):
    _set(monkeypatch, environment="development", encryption_mode="none")
    ensure_encryption_declared()  # no raise


def test_dev_with_infrastructure_passes(monkeypatch):
    _set(monkeypatch, environment="development", encryption_mode="infrastructure")
    ensure_encryption_declared()


def test_prod_with_none_raises(monkeypatch):
    _set(monkeypatch, environment="production", encryption_mode="none")
    with pytest.raises(RuntimeError, match="ENCRYPTION_MODE is 'none'"):
        ensure_encryption_declared()


def test_staging_with_none_raises(monkeypatch):
    _set(monkeypatch, environment="staging", encryption_mode="none")
    with pytest.raises(RuntimeError, match="ENCRYPTION_MODE is 'none'"):
        ensure_encryption_declared()


def test_prod_with_infrastructure_passes(monkeypatch):
    _set(monkeypatch, environment="production", encryption_mode="infrastructure")
    ensure_encryption_declared()


def test_invalid_mode_raises_in_any_env(monkeypatch):
    _set(monkeypatch, environment="development", encryption_mode="rot13")
    with pytest.raises(RuntimeError, match="not a recognised value"):
        ensure_encryption_declared()


def test_case_insensitive_mode(monkeypatch):
    _set(monkeypatch, environment="PRODUCTION", encryption_mode="INFRASTRUCTURE")
    ensure_encryption_declared()


def test_whitespace_in_mode_is_trimmed(monkeypatch):
    _set(monkeypatch, environment="production", encryption_mode="  infrastructure  ")
    ensure_encryption_declared()


def test_empty_mode_raises(monkeypatch):
    _set(monkeypatch, environment="development", encryption_mode="")
    with pytest.raises(RuntimeError, match="not a recognised value"):
        ensure_encryption_declared()


def test_dev_with_none_emits_warning(monkeypatch, caplog):
    _set(monkeypatch, environment="development", encryption_mode="none")
    with caplog.at_level(logging.WARNING, logger="bimguard.security"):
        ensure_encryption_declared()
    assert any("ENCRYPTION_MODE is 'none'" in r.message for r in caplog.records)


def test_prod_with_infrastructure_emits_info(monkeypatch, caplog):
    _set(monkeypatch, environment="production", encryption_mode="infrastructure")
    with caplog.at_level(logging.INFO, logger="bimguard.security"):
        ensure_encryption_declared()
    assert any("operator has declared at-rest encryption" in r.message for r in caplog.records)


def test_app_imports_with_default_dev_config():
    """The test env is development + none, so app import must not raise."""
    from app.main import app  # noqa: F401