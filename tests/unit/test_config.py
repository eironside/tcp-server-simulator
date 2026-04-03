import pytest

from tcp_sim.config.config import load_default_config


@pytest.mark.unit
def test_default_config_contains_schema_version() -> None:
    cfg = load_default_config()
    assert cfg["schema_version"] == 1
