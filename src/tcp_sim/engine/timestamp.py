"""Timestamp parsing and rewrite helpers."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

FORMAT_ISO8601 = "iso8601"
FORMAT_EPOCH_MILLIS = "epoch_millis"
FORMAT_EPOCH_SECONDS_INT = "epoch_seconds_int"
FORMAT_EPOCH_SECONDS_FRACTIONAL = "epoch_seconds_fractional"


def parse_timestamp(raw_value: str, timestamp_format: str) -> datetime:
    value = raw_value.strip()

    if timestamp_format == FORMAT_ISO8601:
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    if timestamp_format == FORMAT_EPOCH_MILLIS:
        millis = int(value)
        return datetime.fromtimestamp(millis / 1000.0, tz=timezone.utc)

    if timestamp_format == FORMAT_EPOCH_SECONDS_INT:
        seconds = int(value)
        return datetime.fromtimestamp(seconds, tz=timezone.utc)

    if timestamp_format == FORMAT_EPOCH_SECONDS_FRACTIONAL:
        seconds = float(value)
        return datetime.fromtimestamp(seconds, tz=timezone.utc)

    raise ValueError(f"Unsupported timestamp format: {timestamp_format}")


def format_timestamp(value: datetime, timestamp_format: str) -> str:
    dt = value.astimezone(timezone.utc)

    if timestamp_format == FORMAT_ISO8601:
        return dt.isoformat().replace("+00:00", "Z")

    if timestamp_format == FORMAT_EPOCH_MILLIS:
        return str(int(dt.timestamp() * 1000.0))

    if timestamp_format == FORMAT_EPOCH_SECONDS_INT:
        return str(int(dt.timestamp()))

    if timestamp_format == FORMAT_EPOCH_SECONDS_FRACTIONAL:
        return f"{dt.timestamp():.6f}".rstrip("0").rstrip(".")

    raise ValueError(f"Unsupported timestamp format: {timestamp_format}")


@dataclass
class TimestampRewriter:
    """Rewrite row timestamps while preserving original relative offsets."""

    timestamp_format: str
    _base_original: datetime | None = None
    _base_monotonic: float | None = None

    def rewrite(self, raw_value: str) -> str:
        parsed = parse_timestamp(raw_value, self.timestamp_format)

        if self._base_original is None:
            self._base_original = parsed
            self._base_monotonic = time.monotonic()

        assert self._base_original is not None
        assert self._base_monotonic is not None

        offset_seconds = (parsed - self._base_original).total_seconds()
        current_utc = datetime.now(timezone.utc)
        rewritten = current_utc + timedelta_seconds(offset_seconds)
        return format_timestamp(rewritten, self.timestamp_format)


def timedelta_seconds(seconds: float) -> timedelta:
    return timedelta(seconds=seconds)


def rewrite_timestamp(raw_value: str, timestamp_format: str = FORMAT_ISO8601) -> str:
    """Single-value rewrite helper preserving previous API compatibility."""
    rewriter = TimestampRewriter(timestamp_format=timestamp_format)
    return rewriter.rewrite(raw_value)
