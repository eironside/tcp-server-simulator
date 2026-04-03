from datetime import timezone

import pytest

from tcp_sim.engine.timestamp import (
    FORMAT_EPOCH_MILLIS,
    FORMAT_EPOCH_SECONDS_FRACTIONAL,
    FORMAT_EPOCH_SECONDS_INT,
    FORMAT_ISO8601,
    TimestampRewriter,
    format_timestamp,
    parse_timestamp,
)


@pytest.mark.unit
def test_parse_and_format_iso8601() -> None:
    value = "2026-04-02T10:00:00Z"
    parsed = parse_timestamp(value, FORMAT_ISO8601)
    assert parsed.tzinfo == timezone.utc
    assert format_timestamp(parsed, FORMAT_ISO8601).startswith("2026-04-02T10:00:00")


@pytest.mark.unit
def test_parse_epoch_formats() -> None:
    millis = parse_timestamp("1712052000000", FORMAT_EPOCH_MILLIS)
    seconds_int = parse_timestamp("1712052000", FORMAT_EPOCH_SECONDS_INT)
    seconds_fractional = parse_timestamp(
        "1712052000.5", FORMAT_EPOCH_SECONDS_FRACTIONAL
    )

    assert int(millis.timestamp()) == 1712052000
    assert int(seconds_int.timestamp()) == 1712052000
    assert seconds_fractional.timestamp() == pytest.approx(1712052000.5)


@pytest.mark.unit
def test_timestamp_rewriter_preserves_relative_offset() -> None:
    rewriter = TimestampRewriter(timestamp_format=FORMAT_EPOCH_SECONDS_INT)
    first = int(rewriter.rewrite("100"))
    second = int(rewriter.rewrite("105"))

    assert second - first == 5
    assert second - first == 5
