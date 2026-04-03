import time
import tracemalloc

import pytest

from tcp_sim.engine.file_reader import FileReader
from tests.scenario_thresholds import (
    TM_SOAK_01_DATA_ROWS,
    TM_SOAK_01_DURATION_SECONDS,
    TM_SOAK_01_MAX_MEMORY_DELTA_BYTES,
    TM_SOAK_01_MIN_PASSES,
    TM_SOAK_01_MIN_ROWS_PER_SECOND,
)


@pytest.mark.soak
def test_large_file_streaming_stability_baseline(tmp_path) -> None:
    data_path = tmp_path / "large.csv"

    with data_path.open("w", encoding="utf-8", newline="") as handle:
        handle.write("id,value\n")
        for idx in range(TM_SOAK_01_DATA_ROWS):
            handle.write(f"{idx},v{idx}\n")

    reader = FileReader(data_path, delimiter=",", has_header=True)
    target_duration = max(TM_SOAK_01_DURATION_SECONDS, 0.1)

    tracemalloc.start()
    snapshot_before = tracemalloc.take_snapshot()
    started_at = time.perf_counter()

    pass_count = 0
    rows_processed = 0

    while True:
        rows_processed += sum(1 for _ in reader.iter_valid_rows())
        pass_count += 1
        if time.perf_counter() - started_at >= target_duration:
            break

    snapshot_after = tracemalloc.take_snapshot()
    tracemalloc.stop()
    elapsed_seconds = max(time.perf_counter() - started_at, 0.001)

    mem_before = sum(stat.size for stat in snapshot_before.statistics("filename"))
    mem_after = sum(stat.size for stat in snapshot_after.statistics("filename"))
    memory_delta = mem_after - mem_before
    rows_per_second = rows_processed / elapsed_seconds

    assert pass_count >= TM_SOAK_01_MIN_PASSES
    assert rows_processed >= TM_SOAK_01_DATA_ROWS
    assert memory_delta <= TM_SOAK_01_MAX_MEMORY_DELTA_BYTES
    assert rows_per_second >= TM_SOAK_01_MIN_ROWS_PER_SECOND

    data_path.unlink()
    assert not data_path.exists()
    assert not data_path.exists()
