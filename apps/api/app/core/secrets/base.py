"""Base interface and errors for secret providers."""
from __future__ import annotations

from abc import ABC, abstractmethod


class SecretProviderError(Exception):
    """A secret could not be retrieved. Message is safe to show to users."""


class SecretNotFound(SecretProviderError):
    """The named secret does not exist in the provider."""


class SecretProvider(ABC):
    @abstractmethod
    def get(self, name: str) -> str:
        """Return the secret value. Raises SecretNotFound or SecretProviderError."""

    @property
    def name(self) -> str:
        return type(self).__name__