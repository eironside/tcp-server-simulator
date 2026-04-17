"""Configuration schema and migration utilities."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CURRENT_SCHEMA_VERSION = 2

DEFAULT_RECEIVER_CONFIG: dict[str, Any] = {
    "framing_mode": "lf",
    "max_record_bytes": 1048576,
    "udp_multicast_group": None,
    "udp_multicast_interface": "0.0.0.0",
    "udp_client_hello_payload": None,
    "udp_client_hello_interval_seconds": 0.0,
    "udp_client_filter_remote_peer": False,
    "sink": {
        "enabled": False,
        "path": None,
        "format": "jsonl",
        "record_separator": "\n",
        "rotation_max_bytes": 104857600,
        "rotation_backup_count": 5,
        "queue_high_watermark_bytes": 8388608,
        "queue_low_watermark_bytes": 2097152,
        "queue_max_bytes": 33554432,
    },
}

DEFAULT_CONFIG: dict[str, Any] = {
    "schema_version": CURRENT_SCHEMA_VERSION,
    "role": "sender",
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
    "start_line": None,
    "end_line": None,
    "first_n_lines": None,
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
    "use_tls": False,
    "tls_certfile": None,
    "tls_keyfile": None,
    "tls_ca_file": None,
    "tls_verify": True,
    "tls_server_hostname": None,
    "log_rotation_max_bytes": 10485760,
    "log_rotation_backup_count": 5,
    "udp_recipient_mode": "reply_to_senders",
    "udp_recipient_cache_ttl_seconds": 300,
    "udp_recipient_cache_max_entries": 256,
    "udp_recipient_cache_cleanup_interval_seconds": 30,
    "udp_recipient_cache_eviction_policy": "lru",
    "receiver": DEFAULT_RECEIVER_CONFIG,
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
    # Ensure nested receiver block is populated even if the source config
    # only provided a partial override.
    receiver = merged.get("receiver")
    if not isinstance(receiver, dict):
        receiver = {}
    normalized_receiver = dict(DEFAULT_RECEIVER_CONFIG)
    normalized_receiver.update(receiver)
    sink_override = receiver.get("sink") if isinstance(receiver, dict) else None
    normalized_sink = dict(DEFAULT_RECEIVER_CONFIG["sink"])
    if isinstance(sink_override, dict):
        normalized_sink.update(sink_override)
    normalized_receiver["sink"] = normalized_sink
    merged["receiver"] = normalized_receiver
    return merged


def _migrate_v0_to_v1(raw: dict[str, Any]) -> dict[str, Any]:
    migrated = dict(raw)
    if "rate_fps" in migrated and "rate_features_per_second" not in migrated:
        migrated["rate_features_per_second"] = migrated.pop("rate_fps")

    if (
        "max_reconnect_backoff_seconds" in migrated
        and "reconnect_max_backoff_seconds" not in migrated
    ):
        migrated["reconnect_max_backoff_seconds"] = migrated.pop(
            "max_reconnect_backoff_seconds"
        )

    migrated["schema_version"] = 1
    return migrated


def _migrate_v1_to_v2(raw: dict[str, Any]) -> dict[str, Any]:
    # v1 -> v2: introduce the `role` field (default "sender" to preserve
    # pre-receiver behaviour) and the `receiver` sub-object.
    migrated = dict(raw)
    migrated.setdefault("role", "sender")
    migrated.setdefault("receiver", dict(DEFAULT_RECEIVER_CONFIG))
    migrated["schema_version"] = 2
    return migrated


def migrate_config(
    raw: dict[str, Any],
) -> tuple[dict[str, Any], list[str], bool, int | None]:
    warnings: list[str] = []

    version_value = raw.get("schema_version", 0)
    if not isinstance(version_value, int):
        raise ConfigError("schema_version must be an integer")

    if version_value == CURRENT_SCHEMA_VERSION:
        return _normalize_config(raw), warnings, False, version_value

    if version_value > CURRENT_SCHEMA_VERSION:
        raise ConfigError(
            f"Unsupported future schema version: {version_value}. "
            f"Current supported version is {CURRENT_SCHEMA_VERSION}."
        )

    migrated = dict(raw)
    migrated_any = False
    if version_value == 0:
        migrated = _migrate_v0_to_v1(migrated)
        warnings.append("Migrated config schema from v0 to v1.")
        migrated_any = True
    if migrated.get("schema_version") == 1:
        migrated = _migrate_v1_to_v2(migrated)
        warnings.append("Migrated config schema from v1 to v2.")
        migrated_any = True

    if not migrated_any:
        raise ConfigError(f"Unsupported legacy schema version: {version_value}.")

    return _normalize_config(migrated), warnings, True, version_value


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
        migrated_config, warnings, migrated, source_version = migrate_config(
            raw_payload
        )
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
