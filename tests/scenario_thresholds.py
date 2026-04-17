"""Shared threshold helpers for MVP matrix test scenarios."""

from __future__ import annotations

import os


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


TM_INT_01_CONNECTION_ROUNDS = _env_int("TM_INT_01_CONNECTION_ROUNDS", 40)
TM_INT_01_MIN_SUCCESS_RATIO = _env_float("TM_INT_01_MIN_SUCCESS_RATIO", 0.995)
TM_INT_01_MAX_MEMORY_DELTA_BYTES = _env_int(
    "TM_INT_01_MAX_MEMORY_DELTA_BYTES", 6_000_000
)
TM_INT_01_MAX_ELAPSED_SECONDS = _env_float("TM_INT_01_MAX_ELAPSED_SECONDS", 20.0)

TM_INT_02_FLAP_CYCLES = _env_int("TM_INT_02_FLAP_CYCLES", 5)
TM_INT_02_MAX_RECOVERY_SECONDS = _env_float("TM_INT_02_MAX_RECOVERY_SECONDS", 1.5)
TM_INT_02_MIN_RECONNECT_EVENTS = _env_int("TM_INT_02_MIN_RECONNECT_EVENTS", 3)

TM_INT_03_BROADCAST_ITERATIONS = _env_int("TM_INT_03_BROADCAST_ITERATIONS", 20)
TM_INT_03_MAX_BROADCAST_SECONDS = _env_float("TM_INT_03_MAX_BROADCAST_SECONDS", 6.0)
TM_INT_03_MIN_FAST_BYTES = _env_int("TM_INT_03_MIN_FAST_BYTES", 4096)

TM_SOAK_01_DURATION_SECONDS = _env_float("TM_SOAK_01_DURATION_SECONDS", 1.0)
TM_SOAK_01_DATA_ROWS = _env_int("TM_SOAK_01_DATA_ROWS", 25_000)
TM_SOAK_01_MIN_PASSES = _env_int("TM_SOAK_01_MIN_PASSES", 1)
TM_SOAK_01_MAX_MEMORY_DELTA_BYTES = _env_int(
    "TM_SOAK_01_MAX_MEMORY_DELTA_BYTES", 30_000_000
)
TM_SOAK_01_MIN_ROWS_PER_SECOND = _env_float("TM_SOAK_01_MIN_ROWS_PER_SECOND", 1000.0)

TM_SOAK_02_DURATION_SECONDS = _env_float("TM_SOAK_02_DURATION_SECONDS", 1.0)
TM_SOAK_02_UNIQUE_SENDERS = _env_int("TM_SOAK_02_UNIQUE_SENDERS", 400)
TM_SOAK_02_MAX_MEMORY_DELTA_BYTES = _env_int(
    "TM_SOAK_02_MAX_MEMORY_DELTA_BYTES", 10_000_000
)

TM_SOAK_03_DURATION_SECONDS = _env_float("TM_SOAK_03_DURATION_SECONDS", 1.5)
TM_SOAK_03_PEER_COUNT = _env_int("TM_SOAK_03_PEER_COUNT", 20)
TM_SOAK_03_AGGREGATE_RATE = _env_float("TM_SOAK_03_AGGREGATE_RATE", 500.0)
TM_SOAK_03_MIN_ROTATIONS = _env_int("TM_SOAK_03_MIN_ROTATIONS", 2)
TM_SOAK_03_MAX_MEMORY_DELTA_BYTES = _env_int(
    "TM_SOAK_03_MAX_MEMORY_DELTA_BYTES", 20_000_000
)
