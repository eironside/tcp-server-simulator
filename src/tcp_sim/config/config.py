"""Configuration schema and migration utilities."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

CURRENT_SCHEMA_VERSION = 1

DEFAULT_CONFIG: dict[str, Any] = {
    "schema_version": CURRENT_SCHEMA_VERSION,
    "mode": "server",
    "protocol": "tcp",
    "host": "0.0.0.0",
    "port": 5565,
    "file": "data/sample.csv",
    "delimiter": ",",
    "has_header": True,
    "send_header": True,
    "rate_features_per_second": 10,
    "loop": True,
    "timestamp_field": 3,
    "timestamp_format": "iso8601",
    "replace_timestamp": True,
    "line_ending": "\n",
    "log_file": "tcp-sim.log",
    "log_level": "INFO",
    "connect_timeout_seconds": 10,
    "send_timeout_seconds": 10,
    "slow_client_timeout_seconds": 10,
    "reconnect_max_backoff_seconds": 30,
    "client_queue_high_watermark_bytes": 262144,
    "client_queue_low_watermark_bytes": 131072,
    "client_queue_hard_cap_bytes": 524288,
    "log_rotation_max_bytes": 10485760,
    "log_rotation_backup_count": 5,
    "udp_recipient_mode": "reply_to_senders",
    "udp_recipient_cache_ttl_seconds": 300,
    "udp_recipient_cache_max_entries": 256,
    "udp_recipient_cache_cleanup_interval_seconds": 30,
    "udp_recipient_cache_eviction_policy": "lru",
}


class ConfigError(Exception):
    """Raised when a config payload is invalid or incompatible."""


@dataclass(frozen=True)
class ConfigLoadResult:
    config: dict[str, Any]
    warnings: list[str]
    used_defaults: bool
    migrated: bool
    source_version: int | None


def load_default_config() -> dict[str, Any]:
    return dict(DEFAULT_CONFIG)


def _normalize_config(raw: dict[str, Any]) -> dict[str, Any]:
    merged = load_default_config()
    merged.update(raw)
    merged["schema_version"] = CURRENT_SCHEMA_VERSION
    return merged


def _migrate_v0_to_v1(raw: dict[str, Any]) -> dict[str, Any]:
    migrated = dict(raw)
    if "rate_fps" in migrated and "rate_features_per_second" not in migrated:
        migrated["rate_features_per_second"] = migrated.pop("rate_fps")

    if "max_reconnect_backoff_seconds" in migrated and "reconnect_max_backoff_seconds" not in migrated:
        migrated["reconnect_max_backoff_seconds"] = migrated.pop(
            "max_reconnect_backoff_seconds"
        )

    migrated["schema_version"] = CURRENT_SCHEMA_VERSION
    return _normalize_config(migrated)


def migrate_config(raw: dict[str, Any]) -> tuple[dict[str, Any], list[str], bool, int | None]:
    warnings: list[str] = []

    version_value = raw.get("schema_version", 0)
    if not isinstance(version_value, int):
        raise ConfigError("schema_version must be an integer")

    if version_value == CURRENT_SCHEMA_VERSION:
        return _normalize_config(raw), warnings, False, version_value

    if version_value == 0:
        warnings.append("Migrated config schema from v0 to v1.")
        return _migrate_v0_to_v1(raw), warnings, True, version_value

    if version_value > CURRENT_SCHEMA_VERSION:
        raise ConfigError(
            f"Unsupported future schema version: {version_value}. "
            f"Current supported version is {CURRENT_SCHEMA_VERSION}."
        )

    raise ConfigError(f"Unsupported legacy schema version: {version_value}.")


def load_config_file(path: str | Path) -> ConfigLoadResult:
    config_path = Path(path)

    if not config_path.exists():
        return ConfigLoadResult(
            config=load_default_config(),
            warnings=[f"Config file not found: {config_path}. Using defaults."],
            used_defaults=True,
            migrated=False,
            source_version=None,
        )

    try:
        raw_payload = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return ConfigLoadResult(
            config=load_default_config(),
            warnings=[f"Invalid JSON in config file: {exc}. Using defaults."],
            used_defaults=True,
            migrated=False,
            source_version=None,
        )

    if not isinstance(raw_payload, dict):
        return ConfigLoadResult(
            config=load_default_config(),
            warnings=["Config payload must be a JSON object. Using defaults."],
            used_defaults=True,
            migrated=False,
            source_version=None,
        )

    try:
        migrated_config, warnings, migrated, source_version = migrate_config(raw_payload)
    except ConfigError as exc:
        return ConfigLoadResult(
            config=load_default_config(),
            warnings=[f"{exc} Falling back to defaults."],
            used_defaults=True,
            migrated=False,
            source_version=None,
        )

    return ConfigLoadResult(
        config=migrated_config,
        warnings=warnings,
        used_defaults=False,
        migrated=migrated,
        source_version=source_version,
    )


def save_config_file(path: str | Path, config: dict[str, Any]) -> None:
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    normalized = _normalize_config(config)
    out_path.write_text(
        json.dumps(normalized, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
