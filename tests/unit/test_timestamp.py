import pytest

from tcp_sim.engine.timestamp import rewrite_timestamp


@pytest.mark.unit
def test_timestamp_placeholder_returns_original_value() -> None:
    original = "2026-04-02T10:00:00Z"
    assert rewrite_timestamp(original) == original
