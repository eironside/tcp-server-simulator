import pytest

from tcp_sim.config.config import (
    CURRENT_SCHEMA_VERSION,
    load_config_file,
    load_default_config,
    save_config_file,
)


@pytest.mark.unit
def test_default_config_contains_schema_version() -> None:
    cfg = load_default_config()
    assert cfg["schema_version"] == CURRENT_SCHEMA_VERSION
    assert cfg["start_line"] is None
    assert cfg["end_line"] is None
    assert cfg["first_n_lines"] is None


@pytest.mark.unit
def test_save_and_load_round_trip(tmp_path) -> None:
    config_path = tmp_path / "config.json"
    save_config_file(config_path, {"mode": "client", "port": 6500})

    result = load_config_file(config_path)
    assert result.used_defaults is False
    assert result.config["mode"] == "client"
    assert result.config["port"] == 6500


@pytest.mark.unit
def test_migrate_v0_config(tmp_path) -> None:
    config_path = tmp_path / "legacy.json"
    config_path.write_text(
        """
        {
          "schema_version": 0,
          "rate_fps": 25,
          "max_reconnect_backoff_seconds": 12
        }
        """.strip(),
        encoding="utf-8",
    )

    result = load_config_file(config_path)
    assert result.used_defaults is False
    assert result.migrated is True
    assert result.config["rate_features_per_second"] == 25
    assert result.config["reconnect_max_backoff_seconds"] == 12
    assert result.config["schema_version"] == CURRENT_SCHEMA_VERSION


@pytest.mark.unit
def test_unknown_schema_uses_defaults(tmp_path) -> None:
    config_path = tmp_path / "future.json"
    config_path.write_text('{"schema_version": 99}', encoding="utf-8")

    result = load_config_file(config_path)
    assert result.used_defaults is True
    assert result.config["schema_version"] == CURRENT_SCHEMA_VERSION
    assert result.warnings
