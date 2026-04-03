"""Configuration defaults placeholder for Phase 1."""

from __future__ import annotations

DEFAULT_CONFIG: dict[str, object] = {
    "schema_version": 1,
    "mode": "server",
    "protocol": "tcp",
    "host": "0.0.0.0",
    "port": 5565,
    "rate_features_per_second": 10,
}


def load_default_config() -> dict[str, object]:
    return dict(DEFAULT_CONFIG)
