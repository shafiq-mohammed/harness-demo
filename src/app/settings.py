"""Application settings, built from the environment."""

import os
from dataclasses import dataclass, field

API_KEYS_ENV_VAR = "LINKS_API_KEYS"


@dataclass(frozen=True)
class Settings:
    """Immutable configuration for one application instance."""

    api_keys: frozenset[str] = field(default_factory=frozenset)

    @classmethod
    def from_env(cls) -> "Settings":
        """Read LINKS_API_KEYS (comma-separated, whitespace stripped, empty entries dropped)."""
        raw = os.environ.get(API_KEYS_ENV_VAR, "")
        keys = frozenset(part.strip() for part in raw.split(",") if part.strip())
        return cls(api_keys=keys)
