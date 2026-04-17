"""Unit tests for v1 -> v2 config migration (adds role + receiver block)."""

from __future__ import annotations

import json

import pytest

from tcp_sim.config.config import (
    CURRENT_SCHEMA_VERSION,
    DEFAULT_RECEIVER_CONFIG,
    load_config_file,
    load_default_config,
    save_config_file,
)


@pytest.mark.unit
def test_default_config_has_role_and_receiver_block() -> None:
    cfg = load_default_config()
    assert cfg["schema_version"] == CURRENT_SCHEMA_VERSION == 2
    assert cfg["role"] == "sender"
    assert "receiver" in cfg
    receiver = cfg["receiver"]
    assert receiver["framing_mode"] == "lf"
    assert receiver["max_record_bytes"] == 1048576
    assert receiver["sink"]["enabled"] is False
    assert receiver["sink"]["format"] == "jsonl"


@pytest.mark.unit
def test_migrate_v1_to_v2_adds_role_and_receiver(tmp_path) -> None:
    config_path = tmp_path / "v1.json"
    config_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "mode": "client",
                "port": 6000,
            }
        ),
        encoding="utf-8",
    )

    result = load_config_file(config_path)
    assert result.migrated is True
    assert result.used_defaults is False
    assert result.source_version == 1
    assert result.config["schema_version"] == 2
    assert result.config["role"] == "sender"
    assert result.config["mode"] == "client"
    assert result.config["port"] == 6000
    assert result.config["receiver"] == DEFAULT_RECEIVER_CONFIG
    assert any("v1 to v2" in w for w in result.warnings)


@pytest.mark.unit
def test_migrate_v0_walks_through_to_v2(tmp_path) -> None:
    config_path = tmp_path / "v0.json"
    config_path.write_text(
        json.dumps(
            {
                "schema_version": 0,
                "rate_fps": 25,
            }
        ),
        encoding="utf-8",
    )

    result = load_config_file(config_path)
    assert result.migrated is True
    assert result.config["schema_version"] == 2
    assert result.config["rate_features_per_second"] == 25
    assert result.config["role"] == "sender"
    assert result.config["receiver"]["framing_mode"] == "lf"
    # Two migration warnings: v0->v1 and v1->v2.
    assert sum("Migrated" in w for w in result.warnings) == 2


@pytest.mark.unit
def test_partial_receiver_override_fills_defaults(tmp_path) -> None:
    config_path = tmp_path / "partial.json"
    save_config_file(
        config_path,
        {
            "role": "receiver",
            "receiver": {
                "framing_mode": "crlf",
                "sink": {"enabled": True, "path": "/tmp/out.jsonl"},
            },
        },
    )
    result = load_config_file(config_path)
    assert result.config["role"] == "receiver"
    receiver = result.config["receiver"]
    assert receiver["framing_mode"] == "crlf"
    # max_record_bytes not specified -> default
    assert receiver["max_record_bytes"] == 1048576
    sink = receiver["sink"]
    assert sink["enabled"] is True
    assert sink["path"] == "/tmp/out.jsonl"
    # Non-specified sink keys fall back to defaults.
    assert sink["format"] == "jsonl"
    assert sink["rotation_backup_count"] == 5


@pytest.mark.unit
def test_save_then_load_round_trip_preserves_receiver_block(tmp_path) -> None:
    config_path = tmp_path / "rt.json"
    save_config_file(
        config_path,
        {
            "role": "receiver",
            "receiver": {
                "framing_mode": "raw_chunk",
                "max_record_bytes": 2048,
                "sink": {"enabled": True, "format": "delimited"},
            },
        },
    )
    result = load_config_file(config_path)
    assert result.config["role"] == "receiver"
    assert result.config["receiver"]["framing_mode"] == "raw_chunk"
    assert result.config["receiver"]["max_record_bytes"] == 2048
    assert result.config["receiver"]["sink"]["format"] == "delimited"
